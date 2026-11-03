import { createClient } from "npm:@supabase/supabase-js@2";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const aiutaApiUrl = "https://api.aiuta.com/digital-try-on/v1";
const imageTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
const terminalStatuses = new Set(["SUCCESS", "FAILED", "CANCELLED", "ABORTED"]);
const guestOperations = new Map<string, {
  id: string;
  aiuta_operation_id: string;
  sku_id: string;
  sku_catalog_name: string;
  status: OperationStatus;
  error: string | null;
  generated_images: Array<{ url: string; expires_at?: string | null }>;
  created_at: string;
  updated_at: string;
}>();

function normalizeGeneratedImages(images: unknown): Array<{ url: string; expires_at?: string | null }> {
  if (!Array.isArray(images)) return [];
  return images.flatMap(image => {
    if (!image || typeof image !== "object" || typeof (image as { url?: unknown }).url !== "string") {
      return [];
    }
    return [{
      url: (image as { url: string }).url,
      expires_at: typeof (image as { expires_at?: unknown }).expires_at === "string"
        ? (image as { expires_at: string }).expires_at
        : null,
    }];
  });
}
type OperationStatus =
  | "CREATING"
  | "CREATED"
  | "IN_PROGRESS"
  | "PAUSED"
  | "SUCCESS"
  | "FAILED"
  | "CANCELLED"
  | "ABORTED";

type AiutaImage = {
  id: string;
  url: string;
};

type AiutaOperation = {
  id: string;
  status: OperationStatus;
  error: string | null;
  abort_reason: string | null;
  generated_images: Array<{ url: string; expires_at?: string | null } | null>;
};

class RequestError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json" },
  });
}

async function aiutaRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${aiutaApiUrl}${path}`, {
    ...init,
    headers: {
      "x-api-key": Deno.env.get("AIUTA_API_KEY")!,
      ...init?.headers,
    },
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload && typeof payload === "object"
      ? (payload.detail ?? payload.message)
      : null;
    throw new Error(
      typeof detail === "string" ? detail : `Aiuta respondió ${response.status}.`,
    );
  }
  return payload as T;
}

Deno.serve(async (request: Request) => {
  if (request.method === "OPTIONS") {
    return new Response("ok", { headers: corsHeaders });
  }
  if (request.method !== "POST") {
    return jsonResponse({ error: "Método no permitido." }, 405);
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL");
  const anonKey = Deno.env.get("SUPABASE_ANON_KEY");
  const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const aiutaApiKey = Deno.env.get("AIUTA_API_KEY");
  if (!supabaseUrl || !anonKey || !serviceRoleKey || !aiutaApiKey) {
    return jsonResponse({ error: "La Edge Function no está configurada." }, 500);
  }

  const authorization = request.headers.get("Authorization");
  const accessToken = authorization?.match(/^Bearer\s+(.+)$/i)?.[1];
  let userId: string | null = null;

  if (accessToken) {
    const authClient = createClient(supabaseUrl, anonKey, {
      auth: { autoRefreshToken: false, persistSession: false },
    });
    const { data: userData, error: authError } = await authClient.auth.getUser(accessToken);
    if (authError || !userData.user) {
      return jsonResponse({ error: "Tu sesión no es válida. Inicia sesión nuevamente." }, 401);
    }
    userId = userData.user.id;
  }

  const database = createClient(supabaseUrl, serviceRoleKey, {
    auth: { autoRefreshToken: false, persistSession: false },
  });

  try {
    const payload = await request.json();
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      throw new RequestError("La solicitud no es válida.", 400);
    }

    if (payload.action === "start") {
      return await startTryOn(database, userId, payload);
    }
    if (payload.action === "status") {
      if (!userId) {
        if (typeof payload.id !== "string" || !guestOperations.has(payload.id)) {
          throw new RequestError("No se encontró la prueba solicitada.", 404);
        }
        const guestRecord = guestOperations.get(payload.id)!;
        const refreshed = await aiutaRequest<AiutaOperation>(
          `/sku_images_operations/${encodeURIComponent(guestRecord.aiuta_operation_id)}`,
        );
        const updated = {
          ...guestRecord,
          status: refreshed.status,
          error: refreshed.error ?? refreshed.abort_reason ?? null,
          generated_images: normalizeGeneratedImages(refreshed.generated_images),
          updated_at: new Date().toISOString(),
        };
        guestOperations.set(payload.id, updated);
        return jsonResponse({ operation: updated });
      }
      return await updateOperation(database, userId, payload.id);
    }
    if (payload.action === "list") {
      if (!userId) {
        const operations = Array.from(guestOperations.values())
          .sort((left, right) => Date.parse(right.created_at) - Date.parse(left.created_at))
          .slice(0, 10);
        return jsonResponse({ operations });
      }
      const { data, error } = await database
        .from("aiuta_try_on_operations")
        .select("id, sku_id, sku_catalog_name, status, generated_images, error, created_at")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(10);
      if (error) throw new Error("No se pudo recuperar el historial de pruebas.");
      return jsonResponse({ operations: data });
    }
    throw new RequestError("La acción solicitada no es válida.", 400);
  } catch (error) {
    const status = error instanceof RequestError ? error.status : 502;
    return jsonResponse(
      { error: error instanceof Error ? error.message : "No se pudo procesar la solicitud." },
      status,
    );
  }
});

async function startTryOn(
  database: ReturnType<typeof createClient>,
  userId: string | null,
  payload: Record<string, unknown>,
): Promise<Response> {
  const skuId = typeof payload.sku_id === "string" ? payload.sku_id.trim() : "";
  const catalogName = typeof payload.sku_catalog_name === "string"
    ? payload.sku_catalog_name.trim()
    : "main";
  const imageData = typeof payload.image_data === "string" ? payload.image_data.trim() : "";
  const imagePath = typeof payload.image_path === "string" ? payload.image_path : "";

  if (!skuId || skuId.length > 256) {
    throw new RequestError("Ingresa un SKU válido de Aiuta.", 400);
  }
  if (!catalogName || catalogName.length > 128) {
    throw new RequestError("El nombre del catálogo no es válido.", 400);
  }

  if (!userId) {
    if (!imageData) {
      throw new RequestError("No se recibió la foto para la prueba sin sesión.", 400);
    }
    const match = imageData.match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,(.+)$/);
    const mimeType = match?.[1] ?? "image/jpeg";
    const encoded = match?.[2] ?? imageData;
    const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
    const blob = new Blob([bytes], { type: mimeType });
    const formData = new FormData();
    formData.append("image_data", blob, "try-on-image");
    const uploaded = await aiutaRequest<AiutaImage>("/uploaded_images", {
      method: "POST",
      body: formData,
    });
    if (!uploaded.id) throw new Error("Aiuta no devolvió el identificador de la foto.");

    const operation = await aiutaRequest<{ operation_id: string; errors: string[] }>(
      "/sku_images_operations",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          uploaded_image_id: uploaded.id,
          sku_id: skuId,
          sku_catalog_name: catalogName,
        }),
      },
    );
    if (operation.errors?.length) throw new Error(operation.errors.join("; "));
    if (!operation.operation_id) {
      throw new Error("Aiuta no devolvió el identificador de la operación.");
    }

    const guestId = crypto.randomUUID();
    const guestRecord = {
      id: guestId,
      aiuta_operation_id: operation.operation_id,
      sku_id: skuId,
      sku_catalog_name: catalogName,
      status: "CREATED" as OperationStatus,
      error: null,
      generated_images: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    guestOperations.set(guestId, guestRecord);
    return jsonResponse({ operation: guestRecord }, 202);
  }

  const imagePathPattern = new RegExp(
    `^${userId}/[0-9a-f-]{36}\.(?:jpg|png|webp)$`,
    "i",
  );
  if (!imagePathPattern.test(imagePath)) {
    throw new RequestError("La foto seleccionada no es válida.", 400);
  }

  const { data: record, error: insertError } = await database
    .from("aiuta_try_on_operations")
    .insert({
      user_id: userId,
      sku_id: skuId,
      sku_catalog_name: catalogName,
      status: "CREATING",
    })
    .select("id, sku_id, sku_catalog_name, status, generated_images, error, created_at")
    .single();
  if (insertError) throw new Error("No se pudo registrar la prueba en la base de datos.");

  try {
    const { data: image, error: downloadError } = await database.storage
      .from("aiuta-try-on-uploads")
      .download(imagePath);
    if (downloadError || !image) {
      throw new Error("No se pudo recuperar la foto para enviarla a Aiuta.");
    }
    if (!imageTypes.has(image.type) || image.size === 0 || image.size > 10 * 1024 * 1024) {
      throw new RequestError("La foto debe ser JPEG, PNG o WebP de hasta 10 MB.", 400);
    }

    const formData = new FormData();
    formData.append("image_data", image, "try-on-image");
    const uploaded = await aiutaRequest<AiutaImage>("/uploaded_images", {
      method: "POST",
      body: formData,
    });
    if (!uploaded.id) throw new Error("Aiuta no devolvió el identificador de la foto.");

    const operation = await aiutaRequest<{ operation_id: string; errors: string[] }>(
      "/sku_images_operations",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          uploaded_image_id: uploaded.id,
          sku_id: skuId,
          sku_catalog_name: catalogName,
        }),
      },
    );
    if (operation.errors?.length) throw new Error(operation.errors.join("; "));
    if (!operation.operation_id) {
      throw new Error("Aiuta no devolvió el identificador de la operación.");
    }

    const { data: updated, error: updateError } = await database
      .from("aiuta_try_on_operations")
      .update({
        aiuta_operation_id: operation.operation_id,
        status: "CREATED",
        updated_at: new Date().toISOString(),
      })
      .eq("id", record.id)
      .select("id, sku_id, sku_catalog_name, status, generated_images, error, created_at")
      .single();
    if (updateError) throw new Error("No se pudo actualizar la prueba en la base de datos.");
    return jsonResponse({ operation: updated }, 202);
  } catch (error) {
    await database
      .from("aiuta_try_on_operations")
      .update({
        status: "FAILED",
        error: error instanceof Error ? error.message.slice(0, 1000) : "Error de Aiuta.",
        updated_at: new Date().toISOString(),
      })
      .eq("id", record.id);
    if (error instanceof RequestError) throw error;
    throw new Error(
      error instanceof Error ? error.message : "No se pudo iniciar la generación en Aiuta.",
    );
  } finally {
    await database.storage.from("aiuta-try-on-uploads").remove([imagePath]);
  }
}


async function updateOperation(
  database: ReturnType<typeof createClient>,
  userId: string,
  id: unknown,
): Promise<Response> {
  if (typeof id !== "string" || !/^[0-9a-f-]{36}$/i.test(id)) {
    throw new RequestError("El identificador de la operación no es válido.", 400);
  }
  const { data: record, error: lookupError } = await database
    .from("aiuta_try_on_operations")
    .select("id, aiuta_operation_id, sku_id, sku_catalog_name, status, generated_images, error, created_at")
    .eq("id", id)
    .eq("user_id", userId)
    .maybeSingle();
  if (lookupError) throw new Error("No se pudo consultar la prueba en la base de datos.");
  if (!record) throw new RequestError("No se encontró la prueba solicitada.", 404);
  if (!record.aiuta_operation_id || terminalStatuses.has(record.status)) {
    return jsonResponse({ operation: record });
  }

  const result = await aiutaRequest<AiutaOperation>(
    `/sku_images_operations/${encodeURIComponent(record.aiuta_operation_id)}`,
  );
  const generatedImages = Array.isArray(result.generated_images)
    ? result.generated_images
      .filter((image): image is NonNullable<typeof image> => Boolean(image?.url))
      .map(image => ({ url: image.url, expires_at: image.expires_at ?? null }))
    : [];
  const { data: updated, error: updateError } = await database
    .from("aiuta_try_on_operations")
    .update({
      status: result.status,
      error: result.error ?? result.abort_reason ?? null,
      generated_images: generatedImages,
      updated_at: new Date().toISOString(),
    })
    .eq("id", id)
    .eq("user_id", userId)
    .select("id, sku_id, sku_catalog_name, status, generated_images, error, created_at")
    .single();
  if (updateError) throw new Error("No se pudo guardar el resultado en la base de datos.");
  return jsonResponse({ operation: updated });
}

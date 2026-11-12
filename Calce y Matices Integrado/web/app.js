const readJsonResponse = async (response, endpoint) => {
  const body = await response.text();
  const contentType = response.headers.get("content-type") || "sin Content-Type";
  if (!body.trim()) {
    throw new Error(
      `${endpoint}: respuesta vacía (HTTP ${response.status}, ${contentType}).`,
    );
  }
  try {
    return JSON.parse(body);
  } catch (error) {
    if (error instanceof SyntaxError) {
      throw new Error(
        `${endpoint}: respuesta no JSON (HTTP ${response.status}, ${contentType}).`,
      );
    }
    throw error;
  }
};

document.querySelectorAll(".product-image").forEach(image => {
  image.addEventListener("error", () => {
    const link = image.closest(".product-image-link");
    if (!link) return;

    const placeholder = document.createElement("div");
    placeholder.className = "product-image-placeholder";
    placeholder.setAttribute("role", "img");
    placeholder.setAttribute("aria-label", "Foto de referencia de Vestua no disponible");
    placeholder.textContent = "Foto de referencia no disponible";
    link.replaceWith(placeholder);
  }, { once: true });
});

const startupDialogs = Array.from(document.querySelectorAll("[data-startup-dialog]"));

const showStartupDialog = index => {
  if (index >= startupDialogs.length) return;
  const dialog = startupDialogs[index];
  let dismissTimer;
  let closeTimer;
  let isDismissing = false;
  const dismissDialog = () => {
    if (!dialog.open || isDismissing) return;
    isDismissing = true;
    window.clearTimeout(dismissTimer);
    dialog.classList.add("is-dismissing");
    closeTimer = window.setTimeout(() => {
      dialog.close();
      dialog.classList.remove("is-dismissing");
      showStartupDialog(index + 1);
    }, 700);
  };

  dialog.addEventListener("cancel", event => {
    event.preventDefault();
    dismissDialog();
  }, { once: true });
  dialog.addEventListener("click", event => {
    if (event.target === dialog) dismissDialog();
  }, { once: true });
  dialog.showModal();
  dismissTimer = window.setTimeout(dismissDialog, 2000);
  dialog.addEventListener("close", () => {
    window.clearTimeout(dismissTimer);
    window.clearTimeout(closeTimer);
  }, { once: true });
};

const startupVisitKey = "medidas-startup-dialog-seen";
const navigationType = performance.getEntriesByType("navigation")[0]?.type;
const shouldShowStartupDialogs = (
  sessionStorage.getItem(startupVisitKey) !== "true"
  || navigationType === "reload"
);
if (startupDialogs.length && shouldShowStartupDialogs && !document.getElementById("style-wizard")) {
  sessionStorage.setItem(startupVisitKey, "true");
  showStartupDialog(0);
}

const scrollPositionKey = "medidas-scroll-position";
const savedScrollPosition = sessionStorage.getItem(scrollPositionKey);
if (savedScrollPosition !== null) {
  sessionStorage.removeItem(scrollPositionKey);
  const scrollPosition = Number(savedScrollPosition);
  if (Number.isFinite(scrollPosition)) {
    requestAnimationFrame(() => window.scrollTo(0, scrollPosition));
  }
}

document.querySelectorAll('form[action="/"]').forEach(form => {
  const rememberCheckbox = form.querySelector("#remember-me");
  const rememberStatus = form.querySelector("#remember-status");
  const measurementFields = Array.from(
    form.querySelectorAll('.measurement-input[name]')
  );
  const rememberedEnabledKey = "medidas-remember-enabled";
  const rememberedValuesKey = "medidas-remember-values";
  const isCatalogView = new URLSearchParams(window.location.search).get("view") === "catalog";
  const isStyleWizardForm = form.matches("[data-style-wizard-form]");

  const showRememberStatus = message => {
    if (rememberStatus) rememberStatus.textContent = message;
  };
  const showPhotoRememberStatus = message => {
    const photoStatus = document.getElementById("matices-remember-status");
    if (photoStatus) photoStatus.textContent = message;
  };
  const readMeasurementValues = () => Object.fromEntries(
    measurementFields.map(field => [field.name, field.value])
  );
  const saveMeasurements = () => {
    localStorage.setItem(rememberedEnabledKey, "true");
    localStorage.setItem(rememberedValuesKey, JSON.stringify(readMeasurementValues()));
  };

  if (rememberCheckbox) {
    try {
      rememberCheckbox.checked = localStorage.getItem(rememberedEnabledKey) === "true";
      const storedValues = localStorage.getItem(rememberedValuesKey);
      const currentValues = readMeasurementValues();
      const hasCurrentMeasurement = Object.values(currentValues).some(Boolean);
      if (rememberCheckbox.checked && storedValues) {
        const parsedValues = JSON.parse(storedValues);
        if (!parsedValues || typeof parsedValues !== "object" || Array.isArray(parsedValues)) {
          throw new Error("Las medidas recordadas tienen un formato inválido.");
        }
        if (!isCatalogView) {
          measurementFields.forEach(field => {
            if (!field.value && typeof parsedValues[field.name] === "string") {
              field.value = parsedValues[field.name];
            }
          });
          if (!isStyleWizardForm && Object.values(readMeasurementValues()).some(Boolean)) {
            form.requestSubmit();
          }
        }
      }
    } catch (error) {
      rememberCheckbox.checked = false;
      showRememberStatus("No se pudieron recuperar las medidas guardadas.");
      console.error("No se pudieron recuperar las medidas guardadas.", error);
    }

    rememberCheckbox.addEventListener("change", () => {
      try {
        if (rememberCheckbox.checked) {
          saveMeasurements();
          showRememberStatus("Medidas guardadas en este navegador.");
        } else {
          localStorage.removeItem(rememberedEnabledKey);
          localStorage.removeItem(rememberedValuesKey);
          showRememberStatus("Se borraron las medidas guardadas.");
        }
      } catch (error) {
        showRememberStatus("No se pudieron guardar las medidas en este navegador.");
        console.error("No se pudieron actualizar las medidas guardadas.", error);
      }
    });
  }

  form.addEventListener("submit", () => {
    if (!isStyleWizardForm) {
      sessionStorage.setItem(scrollPositionKey, String(window.scrollY));
    }
    if (rememberCheckbox?.checked) {
      try {
        saveMeasurements();
        showRememberStatus("Medidas guardadas en este navegador.");
      } catch (error) {
        showRememberStatus("No se pudieron guardar las medidas en este navegador.");
        console.error("No se pudieron guardar las medidas.", error);
      }
    }
  });
  form.querySelectorAll('input[name], select[name]').forEach(field => {
    field.addEventListener("change", () => {
      if (!isStyleWizardForm) form.requestSubmit();
    });
  });

  measurementFields.forEach(field => {
    field.addEventListener("input", () => {
      if (!rememberCheckbox.checked) return;
      try {
        saveMeasurements();
        showRememberStatus("Medidas guardadas en este navegador.");
      } catch (error) {
        showRememberStatus("No se pudieron guardar las medidas en este navegador.");
        console.error("No se pudieron guardar las medidas.", error);
      }
    });
  });

  const accountStatus = document.getElementById("supabase-auth-status");
  if (accountStatus && isStyleWizardForm) {
    const emailInput = document.getElementById("supabase-email");
    const passwordInput = document.getElementById("supabase-password");
    const confirmPasswordInput = document.getElementById("supabase-password-confirm");
    const rememberSessionInput = document.getElementById("supabase-remember-session");
    const rememberSessionRow = document.querySelector("[data-remember-session-row]");
    const rememberPhotoInput = document.getElementById("matices-remember");
    const confirmPasswordLabel = document.querySelector(".supabase-confirm-password");
    const authDescription = document.querySelector("[data-auth-description]");
    const authForm = document.querySelector("[data-supabase-auth-form]");
    const authModeButtons = Array.from(document.querySelectorAll("[data-auth-mode]"));
    const signInButton = document.querySelector("[data-supabase-sign-in]");
    const signUpButton = document.querySelector("[data-supabase-sign-up]");
    const signOutButton = document.querySelector("[data-supabase-sign-out]");
    const profileMenu = document.querySelector("[data-profile-menu]");
    const profileEmail = document.querySelector("[data-profile-email]");
    const profileEditLink = document.querySelector("[data-profile-edit]");
    const accountLinks = Array.from(document.querySelectorAll("[data-open-account]"));
    const supabaseUrl = document.querySelector('meta[name="supabase-url"]')?.content;
    const supabaseKey = document.querySelector('meta[name="supabase-publishable-key"]')?.content;
    let supabaseClient;
    window.calceGetAccessToken = async () => {
      if (!supabaseClient) return null;
      const { data, error } = await supabaseClient.auth.getSession();
      if (error) throw error;
      return data.session?.access_token ?? null;
    };
    let signedInUser;
    let activeUserId;
    let profileLoadedUserId;
    let latestSelectedPhoto;
    let pendingPhotoRemember;
    let rememberedPhotoPath;
    let profilePhotoSyncQueue = Promise.resolve();
    let cloudSaveTimer;
    const profilePhotoBucket = "user-profile-photos";
    const profilePhotoPath = user => `${user.id}/remembered-photo`;
    let authMode = new URLSearchParams(window.location.search).get("auth_mode") === "sign-up"
      ? "sign-up"
      : "sign-in";

    const showAccountStatus = message => {
      accountStatus.textContent = message;
    };
    const setAuthControls = user => {
      authForm.hidden = Boolean(user);
      profileMenu.hidden = !user;
      signOutButton.hidden = !user;
      profileEditLink.hidden = !user;
      profileEmail.hidden = !user;
      profileEmail.textContent = user?.email || "Cuenta activa";
      accountLinks.forEach(link => {
        link.hidden = Boolean(user);
      });
      emailInput.disabled = Boolean(user);
      passwordInput.disabled = Boolean(user);
      confirmPasswordInput.disabled = Boolean(user);
      rememberSessionInput.disabled = Boolean(user);
      authModeButtons.forEach(button => {
        button.disabled = Boolean(user);
      });
    };
    const setAuthMode = mode => {
      authMode = mode;
      const creatingAccount = mode === "sign-up";
      authModeButtons.forEach(button => {
        const isActive = button.dataset.authMode === mode;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-pressed", String(isActive));
      });
      accountLinks.forEach(link => {
        if (link.dataset.openAccount === mode) {
          link.setAttribute("aria-current", "page");
        } else {
          link.removeAttribute("aria-current");
        }
      });
      confirmPasswordLabel.hidden = !creatingAccount;
      confirmPasswordInput.required = creatingAccount;
      confirmPasswordInput.disabled = !creatingAccount || Boolean(signedInUser);
      rememberSessionRow.hidden = creatingAccount;
      signInButton.hidden = creatingAccount;
      signUpButton.hidden = !creatingAccount;
      passwordInput.autocomplete = creatingAccount ? "new-password" : "current-password";
      authDescription.textContent = creatingAccount
        ? "Crea tu cuenta para conservar tus medidas y paleta en tus próximos dispositivos."
        : "Inicia sesión para sincronizar de forma privada tus medidas y paleta.";
    };
    const authStorage = {
      getItem: async key => {
        const persistentSession = window.localStorage.getItem(key);
        if (persistentSession !== null) {
          rememberSessionInput.checked = true;
          return persistentSession;
        }
        return window.sessionStorage.getItem(key);
      },
      setItem: async (key, value) => {
        const selectedStorage = rememberSessionInput.checked
          ? window.localStorage
          : window.sessionStorage;
        const otherStorage = rememberSessionInput.checked
          ? window.sessionStorage
          : window.localStorage;
        selectedStorage.setItem(key, value);
        otherStorage.removeItem(key);
      },
      removeItem: async key => {
        window.localStorage.removeItem(key);
        window.sessionStorage.removeItem(key);
      },
    };
    const readPalette = () => {
      try {
        const palette = JSON.parse(sessionStorage.getItem("matices-wizard-palette") || "[]");
        return Array.isArray(palette) ? palette : [];
      } catch (error) {
        console.error("No se pudo leer la paleta para sincronizarla.", error);
        return [];
      }
    };
    const saveProfile = async () => {
      if (
        !supabaseClient
        || !signedInUser
        || profileLoadedUserId !== signedInUser.id
      ) return;
      const rememberPhoto = rememberPhotoInput?.checked === true;
      const rememberMeasurements = rememberCheckbox?.checked === true || rememberPhoto;
      if (!rememberMeasurements && !rememberPhoto) {
        rememberedPhotoPath = null;
        const { error } = await supabaseClient
          .from("user_profiles")
          .delete()
          .eq("user_id", signedInUser.id);
        if (error) throw error;
        return;
      }
      const measurements = Object.fromEntries(measurementFields.map(field => [
        field.name,
        rememberMeasurements && field.value ? Number(field.value) : null,
      ]));
      const { error } = await supabaseClient
        .from("user_profiles")
        .upsert({
          user_id: signedInUser.id,
          bust: measurements.bust,
          waist: measurements.waist,
          hip: measurements.hip,
          remember_measurements: rememberMeasurements,
          remember_photo: rememberPhoto,
          photo_path: rememberPhoto ? rememberedPhotoPath : null,
          color_palette: rememberMeasurements ? readPalette() : [],
          updated_at: new Date().toISOString(),
        }, { onConflict: "user_id" });
      if (error) throw error;
      if (rememberMeasurements) {
        showRememberStatus("Medidas y paleta guardadas de forma privada en Supabase.");
      }
    };
    const scheduleProfileSave = () => {
      window.clearTimeout(cloudSaveTimer);
      cloudSaveTimer = window.setTimeout(() => {
        saveProfile().catch(error => {
          showRememberStatus("No se pudieron sincronizar tus datos con Supabase.");
          console.error("No se pudo guardar el perfil en Supabase.", error);
        });
      }, 400);
    };
    const uploadProfilePhoto = async (user, file) => {
      const allowedTypes = new Set([
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
        "image/avif",
      ]);
      if (!allowedTypes.has(file.type)) {
        throw new Error("La foto debe estar en formato JPEG, PNG, WebP, GIF o AVIF.");
      }
      if (file.size > 10 * 1024 * 1024) {
        throw new Error("La foto supera el límite de 10 MB.");
      }
      const { error } = await supabaseClient.storage
        .from(profilePhotoBucket)
        .upload(profilePhotoPath(user), file, {
          cacheControl: "3600",
          contentType: file.type,
          upsert: true,
        });
      if (error) throw error;
      return profilePhotoPath(user);
    };
    const deleteProfilePhoto = async user => {
      const { error } = await supabaseClient.storage
        .from(profilePhotoBucket)
        .remove([profilePhotoPath(user)]);
      if (error) throw error;
    };
    const queueProfilePhotoSync = operation => {
      const task = profilePhotoSyncQueue.then(operation);
      profilePhotoSyncQueue = task.then(() => undefined, () => undefined);
      return task;
    };
    const loadProfile = async user => {
      const { data, error } = await supabaseClient
        .from("user_profiles")
        .select("bust, waist, hip, color_palette, remember_measurements, remember_photo, photo_path")
        .eq("user_id", user.id)
        .maybeSingle();
      if (error) {
        showAccountStatus(`No se pudo recuperar el perfil: ${error.message}`);
        console.error("No se pudo recuperar el perfil de Supabase.", error);
        throw error;
      }
      if (!data) {
        showAccountStatus("Sesión iniciada. Activa «Recordar medidas» para sincronizar tus datos.");
        return false;
      }
      rememberCheckbox.checked = (
        data.remember_measurements === true || data.remember_photo === true
      );
      if (rememberCheckbox.checked) {
        measurementFields.forEach(field => {
          if (typeof data[field.name] === "number") {
            field.value = String(data[field.name]);
            field.dispatchEvent(new Event("input", { bubbles: true }));
          }
        });
        try {
          saveMeasurements();
        } catch (storageError) {
          console.error("No se pudo conservar el perfil en este navegador.", storageError);
        }
      }
      if (Array.isArray(data.color_palette)) {
        window.dispatchEvent(new CustomEvent("matices:restore-palette", {
          detail: { palette: rememberCheckbox.checked ? data.color_palette : [] },
        }));
      }
      rememberPhotoInput.checked = data.remember_photo === true;
      rememberedPhotoPath = data.photo_path;
      if (rememberPhotoInput.checked && rememberedPhotoPath) {
        if (rememberedPhotoPath !== profilePhotoPath(user)) {
          throw new Error("La ruta de la foto del perfil no es válida.");
        }
        const { data: photo, error: photoError } = await supabaseClient.storage
          .from(profilePhotoBucket)
          .download(rememberedPhotoPath);
        if (photoError) throw photoError;
        window.dispatchEvent(new CustomEvent("matices:restore-photo", {
          detail: {
            file: new File([photo], "foto-recordada", {
              type: photo.type || "image/jpeg",
              lastModified: Date.now(),
            }),
          },
        }));
      }
      showAccountStatus("Perfil recuperado de tu cuenta de Supabase.");
      return true;
    };
    const handleAuthSession = async session => {
      const user = session?.user ?? null;
      const userId = user?.id ?? null;
      if (userId === activeUserId) return;
      const previousUserId = activeUserId;
      activeUserId = userId;
      profileLoadedUserId = null;
      signedInUser = user;
      setAuthControls(user);
      if (!user) {
        if (previousUserId) pendingPhotoRemember = false;
        rememberedPhotoPath = null;
        showAccountStatus("No has iniciado sesión. Tus medidas pueden seguir guardándose en este navegador.");
        return;
      }
      showAccountStatus(`Sesión iniciada como ${user.email || "usuario"}. Recuperando perfil…`);
      const hasProfile = await loadProfile(user);
      profileLoadedUserId = user.id;
      if (pendingPhotoRemember) {
        rememberCheckbox.checked = true;
        rememberPhotoInput.checked = true;
        if (latestSelectedPhoto) {
          rememberedPhotoPath = await uploadProfilePhoto(user, latestSelectedPhoto);
        }
        await saveProfile();
        pendingPhotoRemember = false;
      } else if (!hasProfile && (rememberCheckbox?.checked || rememberPhotoInput?.checked)) {
        if (rememberPhotoInput.checked && latestSelectedPhoto) {
          rememberedPhotoPath = await uploadProfilePhoto(user, latestSelectedPhoto);
        }
        await saveProfile();
      }
    };
    const credentials = () => {
      const email = emailInput.value.trim();
      const password = passwordInput.value;
      if (!emailInput.checkValidity() || !passwordInput.checkValidity() || !email || !password) {
        showAccountStatus("Ingresa un correo válido y una contraseña de al menos 8 caracteres.");
        return null;
      }
      if (authMode === "sign-up" && password !== confirmPasswordInput.value) {
        showAccountStatus("Las contraseñas no coinciden.");
        confirmPasswordInput.focus();
        return null;
      }
      return { email, password };
    };
    authModeButtons.forEach(button => {
      button.addEventListener("click", () => {
        setAuthMode(button.dataset.authMode);
        showAccountStatus("");
      });
    });
    document.querySelectorAll("[data-open-account]").forEach(link => {
      link.addEventListener("click", event => {
        const homePanel = document.querySelector('[data-page-panel="home"]');
        if (homePanel?.hidden) return;
        event.preventDefault();
        setAuthMode(link.dataset.openAccount);
        showAccountStatus("");
        window.dispatchEvent(new CustomEvent("calce:open-account"));
        emailInput.focus({ preventScroll: true });
      });
    });
    [emailInput, passwordInput].forEach(input => {
      input.addEventListener("keydown", event => {
        if (event.key !== "Enter") return;
        event.preventDefault();
        (authMode === "sign-up" ? signUpButton : signInButton).click();
      });
    });

    signInButton.addEventListener("click", async () => {
      const values = credentials();
      if (!values || !supabaseClient) return;
      signInButton.disabled = true;
      try {
        const { error } = await supabaseClient.auth.signInWithPassword(values);
        if (error) {
          showAccountStatus(`No se pudo iniciar sesión: ${error.message}`);
          console.error("No se pudo iniciar sesión en Supabase.", error);
        }
      } catch (error) {
        showAccountStatus(`No se pudo iniciar sesión: ${error.message}`);
        console.error("No se pudo iniciar sesión en Supabase.", error);
      } finally {
        signInButton.disabled = false;
      }
    });
    signUpButton.addEventListener("click", async () => {
      const values = credentials();
      if (!values || !supabaseClient) return;
      signUpButton.disabled = true;
      try {
        const { data, error } = await supabaseClient.auth.signUp({
          ...values,
          options: {
            emailRedirectTo: new URL(
              "/?view=account&auth_mode=sign-in",
              window.location.origin,
            ).toString(),
          },
        });
        if (error) {
          showAccountStatus(`No se pudo crear la cuenta: ${error.message}`);
          console.error("No se pudo crear la cuenta de Supabase.", error);
        } else if (!data.session) {
          showAccountStatus("Cuenta creada. Revisa tu correo para confirmar el registro.");
        } else {
          showAccountStatus("Cuenta creada. Recuperando tu perfil…");
        }
      } catch (error) {
        showAccountStatus(`No se pudo crear la cuenta: ${error.message}`);
        console.error("No se pudo crear la cuenta de Supabase.", error);
      } finally {
        signUpButton.disabled = false;
      }
    });
    signOutButton.addEventListener("click", async () => {
      if (!supabaseClient || !signedInUser) return;
      signOutButton.disabled = true;
      window.clearTimeout(cloudSaveTimer);
      try {
        const { error } = await supabaseClient.auth.signOut();
        if (error) {
          showAccountStatus(`No se pudo cerrar sesión: ${error.message}`);
          console.error("No se pudo cerrar la sesión de Supabase.", error);
        } else {
          await handleAuthSession(null);
          profileMenu.open = false;
          passwordInput.value = "";
          confirmPasswordInput.value = "";
          showAccountStatus("Sesión cerrada.");
        }
      } catch (error) {
        showAccountStatus(`No se pudo cerrar sesión: ${error.message}`);
        console.error("No se pudo cerrar la sesión de Supabase.", error);
      } finally {
        signOutButton.disabled = false;
      }
    });
    rememberCheckbox?.addEventListener("change", scheduleProfileSave);
    window.addEventListener("matices:photo-selected", event => {
      latestSelectedPhoto = event.detail?.file;
      if (rememberPhotoInput.checked && !signedInUser) {
        pendingPhotoRemember = true;
      }
      if (
        !latestSelectedPhoto
        || !supabaseClient
        || !signedInUser
        || profileLoadedUserId !== signedInUser.id
        || !rememberPhotoInput.checked
      ) return;
      queueProfilePhotoSync(async () => {
        const user = signedInUser;
        if (!user || profileLoadedUserId !== user.id || !rememberPhotoInput.checked) return false;
        rememberedPhotoPath = await uploadProfilePhoto(user, latestSelectedPhoto);
        await saveProfile();
        return true;
      })
        .then(saved => {
          if (saved) showPhotoRememberStatus("Foto guardada de forma privada en tu cuenta.");
        })
        .catch(error => {
          showPhotoRememberStatus(`No se pudo guardar la foto en tu cuenta: ${error.message}`);
          console.error("No se pudo guardar la foto del perfil en Supabase.", error);
        });
    });
    window.addEventListener("matices:photo-remember-changed", async event => {
      const { enabled, file } = event.detail || {};
      if (enabled) {
        rememberCheckbox.checked = true;
        try {
          saveMeasurements();
        } catch (error) {
          console.error("No se pudieron recordar las medidas en este navegador.", error);
        }
        if (file) latestSelectedPhoto = file;
      }
      if (!signedInUser || profileLoadedUserId !== signedInUser.id) {
        pendingPhotoRemember = enabled === true;
        return;
      }
      if (
        !supabaseClient
        || !signedInUser
      ) return;
      window.clearTimeout(cloudSaveTimer);
      try {
        await queueProfilePhotoSync(async () => {
          const user = signedInUser;
          if (!user || profileLoadedUserId !== user.id) return;
          if (enabled && file) {
            latestSelectedPhoto = file;
            rememberedPhotoPath = await uploadProfilePhoto(user, file);
          } else if (!enabled) {
            await deleteProfilePhoto(user);
            rememberedPhotoPath = null;
          }
          await saveProfile();
        });
        showPhotoRememberStatus(enabled
          ? "La preferencia de foto se sincronizó con tu cuenta."
          : "La foto se eliminó de tu cuenta.");
      } catch (error) {
        showPhotoRememberStatus(`No se pudo sincronizar la foto con tu cuenta: ${error.message}`);
        console.error("No se pudo sincronizar la preferencia de foto.", error);
      }
    });
    window.addEventListener("matices:photo-removed", async () => {
      latestSelectedPhoto = null;
      if (
        !supabaseClient
        || !signedInUser
        || profileLoadedUserId !== signedInUser.id
      ) return;
      window.clearTimeout(cloudSaveTimer);
      try {
        await queueProfilePhotoSync(async () => {
          const user = signedInUser;
          if (!user || profileLoadedUserId !== user.id) return;
          await deleteProfilePhoto(user);
          rememberedPhotoPath = null;
          await saveProfile();
        });
        showPhotoRememberStatus("La foto se eliminó del navegador y de tu cuenta.");
      } catch (error) {
        showPhotoRememberStatus(`No se pudo eliminar la foto de tu cuenta: ${error.message}`);
        console.error("No se pudo eliminar la foto del perfil en Supabase.", error);
      }
    });
    measurementFields.forEach(field => field.addEventListener("input", scheduleProfileSave));
    window.addEventListener("matices:palette-updated", scheduleProfileSave);

    if (!supabaseUrl || !supabaseKey) {
      signInButton.disabled = true;
      signUpButton.disabled = true;
      signOutButton.hidden = true;
      showAccountStatus("Falta configurar SUPABASE_PUBLISHABLE_KEY en el entorno del servidor.");
    } else {
      signInButton.disabled = true;
      signUpButton.disabled = true;
      showAccountStatus("Conectando con el servicio de cuentas…");
      import("https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2/+esm")
        .then(({ createClient }) => {
          supabaseClient = createClient(supabaseUrl, supabaseKey, {
            auth: { storage: authStorage },
          });
          window.calceSupabaseClient = supabaseClient;
          window.dispatchEvent(new CustomEvent("calce:supabase-ready", {
            detail: { client: supabaseClient },
          }));
          supabaseClient.auth.onAuthStateChange((_event, session) => {
            window.setTimeout(() => {
              handleAuthSession(session).catch(error => {
                showAccountStatus(`No se pudo cargar el perfil: ${error.message}`);
                console.error("No se pudo procesar la sesión de Supabase.", error);
              });
            }, 0);
          });
          return supabaseClient.auth.getSession();
        })
        .then(({ data, error }) => {
          if (error) throw error;
          signInButton.disabled = false;
          signUpButton.disabled = false;
          return handleAuthSession(data.session);
        })
        .catch(error => {
          signInButton.disabled = true;
          signUpButton.disabled = true;
          showAccountStatus(`No se pudo conectar con Supabase: ${error.message}`);
          console.error("No se pudo inicializar Supabase.", error);
        });
    }
    setAuthMode(authMode);
  }
});

document.querySelectorAll("[data-carousel]").forEach(carousel => {
  const cards = Array.from(carousel.querySelectorAll("[data-carousel-card]"));
  const previousButton = carousel.querySelector("[data-previous]");
  const nextButton = carousel.querySelector("[data-next]");
  const recommendedButton = carousel.querySelector("[data-recommended]");
  const position = carousel.querySelector("[data-carousel-position]");
  let currentIndex = 0;

  if (!cards.length || !previousButton || !nextButton || !position || !recommendedButton) {
    return;
  }

  const showCard = index => {
    currentIndex = Math.max(0, Math.min(index, cards.length - 1));
    cards.forEach((card, cardIndex) => {
      const isVisible = cardIndex === currentIndex;
      card.hidden = !isVisible;
      card.setAttribute("aria-hidden", String(!isVisible));
    });
    previousButton.disabled = currentIndex === 0;
    nextButton.disabled = currentIndex === cards.length - 1;
    recommendedButton.classList.toggle("active", currentIndex === 0);
    recommendedButton.setAttribute("aria-pressed", String(currentIndex === 0));
    position.textContent = currentIndex === 0
      ? `Recomendado · 1 de ${cards.length}`
      : `Opción ${currentIndex + 1} de ${cards.length}`;
  };

  previousButton.addEventListener("click", () => showCard(currentIndex - 1));
  nextButton.addEventListener("click", () => showCard(currentIndex + 1));
  recommendedButton.addEventListener("click", () => showCard(0));
  showCard(0);
});

document.querySelectorAll("[data-garment-catalog]").forEach(catalog => {
  const sortSelect = catalog.querySelector("[data-catalog-sort]");
  const itemsContainer = catalog.querySelector("[data-catalog-items]");
  const searchInput = catalog.querySelector("[data-catalog-search]");
  const typeFilter = catalog.querySelector("[data-catalog-type-filter]");
  const resultCount = catalog.querySelector("[data-catalog-result-count]");
  const selectionStatus = catalog.querySelector("[data-catalog-selection-status]");
  const compareButton = catalog.querySelector("[data-catalog-compare]");
  const comparison = catalog.querySelector("[data-catalog-comparison]");
  const comparisonItems = catalog.querySelector("[data-catalog-comparison-items]");
  const totalLabel = catalog.querySelector("[data-catalog-total]");
  const pagination = catalog.querySelector("[data-catalog-pagination]");
  let items = Array.from(catalog.querySelectorAll("[data-catalog-card]"));
  const previousPageButton = catalog.querySelector("[data-catalog-previous]");
  const nextPageButton = catalog.querySelector("[data-catalog-next]");
  const pageLabel = catalog.querySelector("[data-catalog-page]");

  if (
    !sortSelect || !itemsContainer || !searchInput ||
    !typeFilter || !resultCount || !selectionStatus ||
    !compareButton || !comparison || !comparisonItems || !totalLabel ||
    !pagination || !previousPageButton || !nextPageButton || !pageLabel
  ) {
    return;
  }

  let currentPage = Number(catalog.dataset.catalogPageIndex) || 0;
  const selectedCards = new Map();
  let requestNumber = 0;
  let activeController;
  let searchTimer;

  const selectedItems = () => Array.from(selectedCards.values());
  const updateSelection = () => {
    const selected = selectedItems();
    selectionStatus.textContent = selected.length === 0
      ? "Ninguna prenda seleccionada"
      : `${selected.length} ${selected.length === 1 ? "prenda seleccionada" : "prendas seleccionadas"}`;
    compareButton.disabled = selected.length === 0;
    compareButton.textContent = selected.length
      ? "Comparar"
      : "Selecciona Productos a Comparar";
  };
  const deselectCard = productId => {
    selectedCards.delete(productId);
    const card = items.find(candidate => candidate.dataset.catalogId === productId);
    const checkbox = card?.querySelector("[data-catalog-select]");
    if (checkbox) checkbox.checked = false;
    updateSelection();
    if (!comparison.hidden) renderComparison();
  };
  const bindCard = item => {
    const productId = item.dataset.catalogId;
    const checkbox = item.querySelector("[data-catalog-select]");
    if (checkbox && productId) {
      checkbox.checked = selectedCards.has(productId);
      checkbox.addEventListener("change", () => {
        if (checkbox.checked) selectedCards.set(productId, item.cloneNode(true));
        else selectedCards.delete(productId);
        updateSelection();
        if (!comparison.hidden) renderComparison();
      });
    }

    const image = item.querySelector(".catalog-image");
    if (!image) return;
    image.addEventListener(
      "error",
      () => {
        selectedCards.delete(productId);
        items = items.filter(candidate => candidate !== item);
        item.remove();
        updateSelection();
        if (!comparison.hidden) renderComparison();
      },
      { once: true },
    );
    if (image.complete && image.naturalWidth === 0) image.dispatchEvent(new Event("error"));
  };
  const renderComparison = () => {
    const selected = selectedItems();
    comparisonItems.replaceChildren();
    if (!selected.length) {
      comparison.hidden = true;
      compareButton.textContent = "Compara prendas";
      updateSelection();
      return;
    }

    const table = document.createElement("table");
    table.className = "catalog-comparison-table";
    const caption = document.createElement("caption");
    caption.textContent = "Detalles, tallas y medidas de las prendas seleccionadas";
    const tableWrap = document.createElement("div");
    tableWrap.className = "catalog-comparison-table-wrap";
    table.append(caption);
    tableWrap.append(table);

    const head = document.createElement("thead");
    const headerRow = document.createElement("tr");
    const detailHeading = document.createElement("th");
    detailHeading.scope = "col";
    detailHeading.textContent = "Detalle";
    headerRow.append(detailHeading);
    selected.forEach(item => {
      const heading = document.createElement("th");
      heading.scope = "col";
      const headerContent = document.createElement("div");
      headerContent.className = "catalog-comparison-header";
      const productLink = document.createElement("a");
      productLink.href = item.querySelector(".catalog-buy-link")?.href ?? "#";
      productLink.target = "_blank";
      productLink.rel = "noopener noreferrer";
      productLink.textContent = item.querySelector(".catalog-item-info h3")?.textContent ?? "Prenda";
      const removeButton = document.createElement("button");
      const productName = item.querySelector(".catalog-item-info h3")?.textContent?.trim() || "Prenda";
      removeButton.type = "button";
      removeButton.className = "catalog-comparison-remove";
      removeButton.title = `Quitar ${productName} de la comparación`;
      removeButton.setAttribute("aria-label", `Quitar ${productName} de la comparación`);
      removeButton.textContent = "−";
      removeButton.addEventListener("click", () => deselectCard(item.dataset.catalogId));
      headerContent.append(productLink, removeButton);
      heading.append(headerContent);
      headerRow.append(heading);
    });
    head.append(headerRow);
    table.append(head);

    const body = document.createElement("tbody");
    const makeRow = (label, readValue) => {
      const row = document.createElement("tr");
      const heading = document.createElement("th");
      heading.scope = "row";
      heading.textContent = label;
      row.append(heading);
      selected.forEach(item => {
        const cell = document.createElement("td");
        cell.textContent = readValue(item);
        row.append(cell);
      });
      body.append(row);
    };
    const measurementFor = (item, name, field) => {
      const measurement = Array.from(
        item.querySelectorAll("[data-comparison-measure]")
      ).find(entry => entry.dataset.comparisonMeasure === name);
      return measurement?.dataset[field] ?? "No disponible";
    };

    makeRow("Tienda", item => item.dataset.catalogStore || "No indicada");
    makeRow(
      "Marca y tipo",
      item => `${item.dataset.catalogBrand || "No indicada"} · ${item.dataset.catalogType || "Ropa"}`
    );
    makeRow("Talla publicada", item => item.dataset.catalogSize || "No indicada");
    makeRow(
      "Precio publicado",
      item => item.querySelector(".catalog-price")?.textContent ?? "No disponible"
    );
    makeRow("Calce estimado", item => item.dataset.catalogFitLabel || "Sin estimación");
    makeRow("Busto · prenda", () => "No informado en la ficha");
    makeRow("Busto · cuerpo", item => item.dataset.catalogBust || "No ingresado");
    makeRow("Cintura · prenda", item => measurementFor(item, "Cintura", "measureGarment"));
    makeRow("Cintura · cuerpo", item => measurementFor(item, "Cintura", "measureBody"));
    makeRow("Holgura · cintura", item => measurementFor(item, "Cintura", "measureEase"));
    makeRow("Cadera · prenda", item => measurementFor(item, "Cadera", "measureGarment"));
    makeRow("Cadera · cuerpo", item => measurementFor(item, "Cadera", "measureBody"));
    makeRow("Holgura · cadera", item => measurementFor(item, "Cadera", "measureEase"));
    makeRow("Referencia de medidas", item => item.dataset.catalogReference || "Sin referencia");
    table.append(body);
    comparisonItems.append(tableWrap);

    let total = 0;
    let allPricesAvailable = true;
    selected.forEach(item => {
      const price = Number(item.dataset.catalogPrice);
      if (Number.isFinite(price) && price > 0) total += price;
      else allPricesAvailable = false;
    });
    totalLabel.textContent = allPricesAvailable
      ? `Total referencial de la selección: $${total.toLocaleString("es-CL")} CLP`
      : "Total no disponible: una o más prendas no tienen precio publicado en los datos consultados.";
    comparison.hidden = false;
    compareButton.textContent = "Ocultar comparación";
  };
  items.forEach(bindCard);

  const loadPage = async page => {
    const requestId = ++requestNumber;
    activeController?.abort();
    activeController = new AbortController();
    const params = new URLSearchParams(window.location.search);
    params.set("search", searchInput.value.trim());
    params.set("type", typeFilter.value);
    params.set("sort", sortSelect.value);
    params.set("page", String(page));

    try {
      const response = await fetch(`/api/catalog?${params}`, {
        signal: activeController.signal,
      });
      if (!response.ok) {
        throw new Error(`El servidor respondió HTTP ${response.status}.`);
      }
      const data = await readJsonResponse(response, "Catálogo");
      if (requestId !== requestNumber) return;
      const template = document.createElement("template");
      template.innerHTML = data.cards;
      itemsContainer.replaceChildren(template.content);
      items = Array.from(itemsContainer.querySelectorAll("[data-catalog-card]"));
      currentPage = data.page;
      catalog.dataset.catalogPageIndex = String(currentPage);
      resultCount.textContent = data.result_text;
      pageLabel.textContent = data.page_text;
      previousPageButton.disabled = currentPage === 0;
      nextPageButton.disabled = currentPage >= data.pages - 1;
      pagination.hidden = data.pages <= 1;
      items.forEach(bindCard);
      updateSelection();
      if (!comparison.hidden) renderComparison();
    } catch (error) {
      if (error.name === "AbortError") return;
      resultCount.textContent = "No se pudo cargar el catálogo. Inténtalo nuevamente.";
      console.error("No se pudo cargar la página del catálogo.", error);
    }
  };

  sortSelect.addEventListener("change", () => loadPage(0));
  searchInput.addEventListener("input", () => {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(() => loadPage(0), 250);
  });
  typeFilter.addEventListener("change", () => loadPage(0));
  previousPageButton.addEventListener("click", () => {
    loadPage(currentPage - 1);
    catalog.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  nextPageButton.addEventListener("click", () => {
    loadPage(currentPage + 1);
    catalog.scrollIntoView({ behavior: "smooth", block: "start" });
  });
  compareButton.addEventListener("click", () => {
    if (comparison.hidden) {
      renderComparison();
    } else {
      comparison.hidden = true;
      compareButton.textContent = "Comparar prendas";
      updateSelection();
    }
  });
  updateSelection();
});

(() => {
  const wizard = document.getElementById("style-wizard");
  if (!wizard) return;

  const fileInput = document.getElementById("matices-photo-input");
  const preview = document.getElementById("matices-preview");
  const previewBox = document.getElementById("matices-preview-box");
  const removePhotoButton = wizard.querySelector("[data-photo-remove]");
  const status = document.getElementById("matices-status");
  const nextButton = document.getElementById("matices-next-step");
  const cameraButton = wizard.querySelector("[data-camera-open]");
  const cameraPanel = wizard.querySelector("[data-camera-panel]");
  const cameraVideo = document.getElementById("matices-camera-video");
  const captureButton = wizard.querySelector("[data-camera-capture]");
  const cancelCameraButton = wizard.querySelector("[data-camera-cancel]");
  const rememberBox = document.getElementById("matices-remember");
  const rememberRow = document.getElementById("matices-remember-row");
  const rememberStatus = document.getElementById("matices-remember-status");
  const paletteSummaryStatus = wizard.querySelector("[data-palette-summary-status]");
  const paletteSummaryColors = wizard.querySelector("[data-palette-summary-colors]");
  const sizeSummaryStatus = wizard.querySelector("[data-size-summary-status]");
  const sizeSummarySizes = wizard.querySelector("[data-size-summary-sizes]");
  const sizeSummaryMeasures = wizard.querySelector("[data-size-summary-measures]");
  const progressFill = document.querySelector("[data-wizard-progress-fill]");
  const progressBar = document.querySelector(".wizard-progress-bar");
  const wizardSteps = Array.from(document.querySelectorAll(".wizard-progress-steps span"));
  const panels = Array.from(wizard.querySelectorAll("[data-wizard-panel]"));
  const accountPanel = wizard.querySelector("[data-account-panel]");
  const accountLinks = Array.from(document.querySelectorAll("[data-open-account]"));
  const stepInput = wizard.querySelector('input[name="wizard_step"]');
  const wizardForm = wizard.querySelector("[data-style-wizard-form]");
  const tryOnLink = document.querySelector("[data-open-try-on]");
  const tryOnPagePanel = document.getElementById("try-on-panel");
  const tryOnPanel = document.querySelector("[data-virtual-try-on]");
  const homePagePanel = document.getElementById("home-panel");
  const catalogPagePanel = document.getElementById("catalog-panel");
  const tryOnProductSearch = tryOnPanel?.querySelector("[data-vton-product-search]");
  const tryOnProductSelect = tryOnPanel?.querySelector("[data-vton-product-select]");
  const tryOnPersonPreview = tryOnPanel?.querySelector("[data-vton-person-preview]");
  const tryOnPersonEmpty = tryOnPanel?.querySelector("[data-vton-person-empty]");
  const tryOnGarmentPreview = tryOnPanel?.querySelector("[data-vton-garment-preview]");
  const tryOnGarmentEmpty = tryOnPanel?.querySelector("[data-vton-garment-empty]");
  const tryOnGenerateButton = tryOnPanel?.querySelector("[data-vton-generate]");
  const tryOnStatus = tryOnPanel?.querySelector("[data-vton-status]");
  const tryOnResult = tryOnPanel?.querySelector("[data-vton-result]");
  const tryOnResultImage = tryOnPanel?.querySelector("[data-vton-result-image]");
  const tryOnResultStatus = tryOnPanel?.querySelector("[data-vton-result-status]");
  const paletteStorageKey = "matices-wizard-palette";
  const rememberedPhotoEnabledKey = "matices-photo-remember-enabled";
  const rememberedPhotoDatabase = "matices-local-data";
  const rememberedPhotoStore = "photos";
  const maxRememberedPhotoSize = 10 * 1024 * 1024;
  const tryOnPhotoSessionKey = "calce-try-on-photo-key";
  const tryOnPhotoLifetime = 60 * 60 * 1000;
  let currentPalette = [];
  let currentStep = 1;
  let selectedPhoto = null;
  let tryOnPhotoSavePromise = Promise.resolve(true);
  let cameraStream = null;
  let tryOnPersonObjectUrl;
  let tryOnSearchTimer;
  let tryOnProductsController;
  let tryOnRequestController;
  let tryOnProductsLoaded = false;

  const setStatus = message => {
    status.textContent = message;
  };

  const syncTryOnPhoto = () => {
    if (tryOnPersonObjectUrl) URL.revokeObjectURL(tryOnPersonObjectUrl);
    tryOnPersonObjectUrl = null;
    if (!selectedPhoto) {
      tryOnPersonPreview.hidden = true;
      tryOnPersonPreview.removeAttribute("src");
      tryOnPersonEmpty.hidden = false;
      if (tryOnGenerateButton) tryOnGenerateButton.disabled = true;
      return;
    }

    tryOnPersonObjectUrl = URL.createObjectURL(selectedPhoto);
    tryOnPersonPreview.src = tryOnPersonObjectUrl;
    tryOnPersonPreview.hidden = false;
    tryOnPersonEmpty.hidden = true;
    if (tryOnGenerateButton) {
      tryOnGenerateButton.disabled = !tryOnProductSelect?.value;
    }
  };

  const loadTryOnProducts = async search => {
    tryOnProductsController?.abort();
    tryOnProductsController = new AbortController();
    tryOnProductSelect.disabled = true;
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "Buscando prendas…";
    tryOnProductSelect.replaceChildren(option);

    try {
      const params = new URLSearchParams({ search });
      const response = await fetch(`/api/vton-products?${params}`, {
        signal: tryOnProductsController.signal,
      });
      const data = await readJsonResponse(response, "Búsqueda del Probador");
      if (!response.ok) {
        throw new Error(data.error || `El servidor respondió HTTP ${response.status}.`);
      }

      const productOptions = (data.products || []).map(product => {
        const productOption = document.createElement("option");
        productOption.value = product.product_url;
        productOption.textContent = [
          product.store,
          product.brand,
          product.title,
          `Talla ${product.size}`,
        ].join(" · ");
        productOption.dataset.imageUrl = product.image_url;
        return productOption;
      });
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = productOptions.length
        ? "Selecciona una prenda"
        : "No encontramos prendas para esa búsqueda";
      tryOnProductSelect.replaceChildren(placeholder, ...productOptions);
      tryOnProductSelect.disabled = false;
      tryOnProductsLoaded = true;
      tryOnProductSelect.dispatchEvent(new Event("change"));
    } catch (error) {
      if (error.name === "AbortError") return;
      tryOnProductsLoaded = false;
      const failedOption = document.createElement("option");
      failedOption.value = "";
      failedOption.textContent = "No se pudo cargar el catálogo";
      tryOnProductSelect.replaceChildren(failedOption);
      tryOnStatus.textContent = "No se pudo cargar el catálogo de prendas. Inténtalo nuevamente.";
      console.error("No se pudieron cargar prendas para la prueba virtual.", error);
    }
  };

  tryOnLink?.addEventListener("click", event => {
    event.preventDefault();
    homePagePanel.hidden = true;
    catalogPagePanel.hidden = true;
    tryOnPagePanel.hidden = false;
    document.getElementById("home-link")?.removeAttribute("aria-current");
    document.getElementById("catalog-link")?.removeAttribute("aria-current");
    tryOnLink.setAttribute("aria-current", "page");
    syncTryOnPhoto();
    if (!selectedPhoto) {
      tryOnStatus.textContent = "Vuelve a Inicio y selecciona una foto para usarla en el Probador.";
    }
    if (!tryOnProductsLoaded) {
      loadTryOnProducts(tryOnProductSearch.value.trim());
    }
    tryOnPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  tryOnProductSearch?.addEventListener("input", () => {
    window.clearTimeout(tryOnSearchTimer);
    tryOnSearchTimer = window.setTimeout(
      () => loadTryOnProducts(tryOnProductSearch.value.trim()),
      250,
    );
  });

  tryOnProductSelect?.addEventListener("change", () => {
    const selectedOption = tryOnProductSelect.selectedOptions[0];
    const imageUrl = selectedOption?.dataset.imageUrl;
    tryOnGarmentPreview.hidden = !imageUrl;
    tryOnGarmentEmpty.hidden = Boolean(imageUrl);
    if (imageUrl) tryOnGarmentPreview.src = imageUrl;
    if (tryOnGenerateButton) {
      tryOnGenerateButton.disabled = !selectedPhoto || !tryOnProductSelect.value;
    }
    tryOnResult.hidden = true;
  });

  const fileAsBase64 = file => new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = typeof reader.result === "string" ? reader.result : "";
      const separator = dataUrl.indexOf(",");
      if (separator < 0) {
        reject(new Error("No se pudo codificar la foto de Inicio."));
        return;
      }
      resolve(dataUrl.slice(separator + 1));
    };
    reader.onerror = () => reject(reader.error || new Error("No se pudo leer la foto de Inicio."));
    reader.readAsDataURL(file);
  });

  tryOnGenerateButton?.addEventListener("click", async () => {
    if (!selectedPhoto || !tryOnProductSelect.value) {
      tryOnStatus.textContent = "Selecciona una foto en Inicio y una prenda del catálogo.";
      return;
    }
    if (selectedPhoto.size > 10 * 1024 * 1024) {
      tryOnStatus.textContent = "La foto debe tener un tamaño máximo de 10 MB.";
      return;
    }

    tryOnRequestController?.abort();
    tryOnRequestController = new AbortController();
    const timeout = window.setTimeout(() => tryOnRequestController.abort(), 60000);
    tryOnGenerateButton.disabled = true;
    tryOnResult.hidden = true;
    tryOnStatus.textContent = "Preparando la simulación; puede tardar unos segundos.";
    try {
      const accessToken = await window.calceGetAccessToken?.();
      if (!accessToken) {
        tryOnStatus.textContent = "Inicia sesión para usar el Probador.";
        return;
      }
      const personImageBase64 = await fileAsBase64(selectedPhoto);
      const response = await fetch("/api/try-on", {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          person_image_base64: personImageBase64,
          product_url: tryOnProductSelect.value,
        }),
        signal: tryOnRequestController.signal,
      });
      const data = await readJsonResponse(response, "Probador");
      if (!response.ok) {
        throw new Error(data.error || `El servidor respondió HTTP ${response.status}.`);
      }
      if (typeof data.result_image_base64 !== "string") {
        throw new Error("Modal no devolvió una imagen válida.");
      }
      tryOnResultImage.src = `data:image/jpeg;base64,${data.result_image_base64}`;
      tryOnResultStatus.textContent = data.detail || "Prueba virtual completada.";
      tryOnResult.hidden = false;
      tryOnStatus.textContent = data.status === "simulation"
        ? "Modo simulación: todavía no se ha integrado la inferencia del modelo VTON."
        : "Prueba virtual completada.";
    } catch (error) {
      tryOnStatus.textContent = error.name === "AbortError"
        ? "La solicitud tardó demasiado y se canceló. Inténtalo nuevamente."
        : error.message || "No se pudo completar la prueba virtual.";
      console.error("No se pudo completar la prueba virtual con Modal.", error);
    } finally {
      window.clearTimeout(timeout);
      if (tryOnGenerateButton) {
        tryOnGenerateButton.disabled = !selectedPhoto || !tryOnProductSelect.value;
      }
    }
  });

  const openPhotoDatabase = () => new Promise((resolve, reject) => {
    const request = indexedDB.open(rememberedPhotoDatabase, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(rememberedPhotoStore);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("No se pudo abrir el almacenamiento local de fotos."));
    request.onblocked = () => reject(new Error("El almacenamiento local de fotos está bloqueado por otra pestaña."));
  });

  const saveRememberedPhoto = async file => {
    const database = await openPhotoDatabase();
    try {
      await new Promise((resolve, reject) => {
        const transaction = database.transaction(rememberedPhotoStore, "readwrite");
        transaction.objectStore(rememberedPhotoStore).put({
          blob: file,
          name: file.name,
          type: file.type,
          lastModified: file.lastModified,
        }, "selected-photo");
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(transaction.error || new Error("No se pudo guardar la foto."));
        transaction.onabort = () => reject(transaction.error || new Error("Se canceló el guardado de la foto."));
      });
    } finally {
      database.close();
    }
  };

  const loadRememberedPhoto = async () => {
    const database = await openPhotoDatabase();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = database.transaction(rememberedPhotoStore, "readonly");
        const request = transaction.objectStore(rememberedPhotoStore).get("selected-photo");
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(request.error || new Error("No se pudo recuperar la foto guardada."));
      });
    } finally {
      database.close();
    }
  };

  const deleteRememberedPhoto = async () => {
    const database = await openPhotoDatabase();
    try {
      await new Promise((resolve, reject) => {
        const transaction = database.transaction(rememberedPhotoStore, "readwrite");
        transaction.objectStore(rememberedPhotoStore).delete("selected-photo");
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(transaction.error || new Error("No se pudo borrar la foto guardada."));
        transaction.onabort = () => reject(transaction.error || new Error("Se canceló el borrado de la foto."));
      });
    } finally {
      database.close();
    }
  };

  const getTryOnPhotoKey = () => {
    let key = sessionStorage.getItem(tryOnPhotoSessionKey);
    if (!key) {
      key = `try-on-session-${crypto.randomUUID()}`;
      sessionStorage.setItem(tryOnPhotoSessionKey, key);
    }
    return key;
  };

  const saveTryOnPhotoForSession = async file => {
    const key = getTryOnPhotoKey();
    const database = await openPhotoDatabase();
    try {
      await new Promise((resolve, reject) => {
        const transaction = database.transaction(rememberedPhotoStore, "readwrite");
        transaction.objectStore(rememberedPhotoStore).put({
          blob: file,
          name: file.name,
          type: file.type,
          lastModified: file.lastModified,
          expiresAt: Date.now() + tryOnPhotoLifetime,
        }, key);
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(
          transaction.error || new Error("No se pudo conservar la foto para el Probador.")
        );
        transaction.onabort = () => reject(
          transaction.error || new Error("Se canceló la preparación de la foto para el Probador.")
        );
      });
    } finally {
      database.close();
    }
  };

  const loadTryOnPhotoForSession = async () => {
    const key = sessionStorage.getItem(tryOnPhotoSessionKey);
    if (!key) return null;
    const database = await openPhotoDatabase();
    try {
      return await new Promise((resolve, reject) => {
        const transaction = database.transaction(rememberedPhotoStore, "readonly");
        const request = transaction.objectStore(rememberedPhotoStore).get(key);
        request.onsuccess = () => resolve(request.result || null);
        request.onerror = () => reject(
          request.error || new Error("No se pudo recuperar la foto para el Probador.")
        );
      });
    } finally {
      database.close();
    }
  };

  const removeTryOnPhotoForSession = async () => {
    const key = sessionStorage.getItem(tryOnPhotoSessionKey);
    sessionStorage.removeItem(tryOnPhotoSessionKey);
    if (!key) return;
    const database = await openPhotoDatabase();
    try {
      await new Promise((resolve, reject) => {
        const transaction = database.transaction(rememberedPhotoStore, "readwrite");
        transaction.objectStore(rememberedPhotoStore).delete(key);
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(
          transaction.error || new Error("No se pudo eliminar la foto temporal.")
        );
      });
    } finally {
      database.close();
    }
  };

  const cleanExpiredTryOnPhotos = async () => {
    const database = await openPhotoDatabase();
    try {
      await new Promise((resolve, reject) => {
        const transaction = database.transaction(rememberedPhotoStore, "readwrite");
        const cursorRequest = transaction.objectStore(rememberedPhotoStore).openCursor();
        cursorRequest.onsuccess = () => {
          const cursor = cursorRequest.result;
          if (!cursor) return;
          const value = cursor.value;
          if (
            typeof cursor.key === "string"
            && cursor.key.startsWith("try-on-session-")
            && Number(value?.expiresAt) <= Date.now()
          ) {
            cursor.delete();
          }
          cursor.continue();
        };
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(
          transaction.error || new Error("No se pudieron limpiar fotos temporales.")
        );
      });
    } finally {
      database.close();
    }
  };

  const persistSelectedPhoto = async (file, notifyAccount = true) => {
    if (!rememberBox?.checked) return;
    if (notifyAccount) {
      window.dispatchEvent(new CustomEvent("matices:photo-selected", {
        detail: { file },
      }));
    }
    try {
      localStorage.setItem(rememberedPhotoEnabledKey, "true");
      await saveRememberedPhoto(file);
      rememberStatus.textContent = file.size > maxRememberedPhotoSize
        ? "Foto guardada en este navegador; supera el límite de 10 MB para la cuenta."
        : "Foto guardada en este navegador.";
    } catch (error) {
      rememberStatus.textContent = "No se pudo guardar la foto en este navegador.";
      console.error("No se pudo guardar la foto recordada.", error);
    }
  };

  const stopCamera = () => {
    cameraStream?.getTracks().forEach(track => track.stop());
    cameraStream = null;
    if (cameraVideo) cameraVideo.srcObject = null;
    if (cameraPanel) cameraPanel.hidden = true;
    if (cameraButton) cameraButton.disabled = false;
  };

  const showSelectedPhoto = (file, persist = true, resetAnalysis = true) => {
    selectedPhoto = file;
    tryOnPhotoSavePromise = saveTryOnPhotoForSession(file)
      .then(() => true)
      .catch(error => {
        console.error("No se pudo conservar la foto para el Probador.", error);
        if (rememberStatus) {
          rememberStatus.textContent = "La foto no se pudo preparar para el Probador en esta sesión.";
        }
        return false;
      });
    syncTryOnPhoto();
    nextButton.disabled = true;
    if (resetAnalysis) {
      currentPalette = [];
      window.dispatchEvent(new CustomEvent("matices:palette-updated"));
      paletteSummaryStatus.textContent = "Completa el análisis de la foto para ver tu paleta.";
      paletteSummaryColors.replaceChildren();
      try {
        sessionStorage.removeItem(paletteStorageKey);
      } catch (error) {
        console.error("No se pudo limpiar la paleta anterior de la sesión.", error);
      }
    }

    const reader = new FileReader();
    reader.onload = () => {
      preview.src = reader.result;
      previewBox.hidden = false;
      rememberRow.hidden = false;
      nextButton.disabled = false;
      setStatus("Foto lista. Presiona Siguiente para analizarla.");
      if (persist) persistSelectedPhoto(file);
    };
    reader.onerror = () => {
      selectedPhoto = null;
      previewBox.hidden = true;
      rememberRow.hidden = true;
      setStatus("No se pudo mostrar la foto. Intenta seleccionarla nuevamente.");
    };
    reader.readAsDataURL(file);
  };

  const restoreRememberedPhoto = async () => {
    try {
      if (localStorage.getItem(rememberedPhotoEnabledKey) !== "true") return;
      rememberBox.checked = true;
      const savedPhoto = await loadRememberedPhoto();
      if (!savedPhoto?.blob) {
        localStorage.removeItem(rememberedPhotoEnabledKey);
        rememberBox.checked = false;
        return;
      }
      const file = new File([savedPhoto.blob], savedPhoto.name || "foto-recordada", {
        type: savedPhoto.type || savedPhoto.blob.type || "image/jpeg",
        lastModified: savedPhoto.lastModified || Date.now(),
      });
      showSelectedPhoto(file, false);
      rememberStatus.textContent = "Foto recuperada de este navegador.";
      if (rememberBox.checked) {
        window.dispatchEvent(new CustomEvent("matices:photo-selected", {
          detail: { file },
        }));
      }
    } catch (error) {
      rememberStatus.textContent = "No se pudo recuperar la foto guardada.";
      console.error("No se pudo recuperar la foto recordada.", error);
    }
  };

  const removeSelectedPhoto = () => {
    window.dispatchEvent(new CustomEvent("matices:photo-removed"));
    selectedPhoto = null;
    syncTryOnPhoto();
    removeTryOnPhotoForSession().catch(error => {
      console.error("No se pudo eliminar la foto temporal del Probador.", error);
    });
    if (fileInput) fileInput.value = "";
    if (preview) preview.removeAttribute("src");
    if (previewBox) previewBox.hidden = true;
    if (rememberRow) rememberRow.hidden = true;
    if (rememberBox) rememberBox.checked = false;
    if (rememberStatus) rememberStatus.textContent = "Eliminando la foto guardada…";
    if (nextButton) nextButton.disabled = true;
    currentPalette = [];
    window.dispatchEvent(new CustomEvent("matices:palette-updated"));
    paletteSummaryStatus.textContent = "Completa el análisis de la foto para ver tu paleta.";
    paletteSummaryColors.replaceChildren();
    try {
      sessionStorage.removeItem(paletteStorageKey);
    } catch (error) {
      console.error("No se pudo eliminar la paleta asociada a la foto.", error);
    }
    try {
      localStorage.removeItem(rememberedPhotoEnabledKey);
      deleteRememberedPhoto().then(() => {
        if (rememberStatus) rememberStatus.textContent = "Foto eliminada del navegador.";
      }).catch(error => {
        if (rememberStatus) rememberStatus.textContent = "No se pudo borrar la foto guardada.";
        console.error("No se pudo borrar la foto recordada.", error);
      });
    } catch (error) {
      if (rememberStatus) rememberStatus.textContent = "No se pudo borrar la foto guardada.";
      console.error("No se pudo borrar la preferencia de foto.", error);
    }
    setStatus("Imagen eliminada. Puedes elegir o tomar otra foto.");
  };

  const updateProgress = step => {
    const steps = Math.max(1, wizardSteps.length);
    const progress = (step / steps) * 100;
    if (progressFill) progressFill.style.width = `${progress}%`;
    if (progressBar) progressBar.setAttribute("aria-valuenow", String(step));
    wizardSteps.forEach((step, index) => {
      step.classList.toggle("is-active", index < currentStep);
    });
  };

  const showStep = step => {
    currentStep = Math.max(1, Math.min(step, panels.length));
    wizard.classList.remove("is-account-view");
    wizard.closest("#home-panel")?.classList.remove("is-account-view");
    if (accountPanel) accountPanel.hidden = true;
    if (currentStep !== 1) stopCamera();
    panels.forEach(panel => {
      panel.hidden = Number(panel.dataset.wizardPanel) !== currentStep;
    });
    const resultsPanel = document.querySelector(".wizard-page-results");
    if (resultsPanel) resultsPanel.hidden = currentStep !== panels.length;
    if (stepInput) stepInput.value = String(currentStep);
    updateProgress(currentStep);
    accountLinks.forEach(link => link.removeAttribute("aria-current"));
    document.getElementById("home-link")?.setAttribute("aria-current", "page");
    wizard.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const showAccount = () => {
    if (!accountPanel) return;
    stopCamera();
    wizard.classList.add("is-account-view");
    wizard.closest("#home-panel")?.classList.add("is-account-view");
    panels.forEach(panel => {
      panel.hidden = true;
    });
    accountPanel.hidden = false;
    const resultsPanel = document.querySelector(".wizard-page-results");
    if (resultsPanel) resultsPanel.hidden = true;
    document.getElementById("home-link")?.removeAttribute("aria-current");
    document.getElementById("catalog-link")?.removeAttribute("aria-current");
    const selectedAuthMode = accountLinks.find(
      link => link.getAttribute("aria-current") === "page",
    )?.dataset.openAccount
      || (new URLSearchParams(window.location.search).get("auth_mode") === "sign-up"
        ? "sign-up"
        : "sign-in");
    accountLinks.forEach(link => {
      if (link.dataset.openAccount === selectedAuthMode) {
        link.setAttribute("aria-current", "page");
      } else {
        link.removeAttribute("aria-current");
      }
    });
    wizard.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  window.addEventListener("calce:open-account", () => {
    showAccount();
  });
  accountPanel?.querySelector("[data-account-back]")?.addEventListener("click", () => {
    showStep(currentStep);
  });

  const rgbToHex = (r, g, b) => [r, g, b].map(value => value.toString(16).padStart(2, "0")).join("").toUpperCase();

  const rgbToHsl = (r, g, b) => {
    const red = r / 255;
    const green = g / 255;
    const blue = b / 255;
    const max = Math.max(red, green, blue);
    const min = Math.min(red, green, blue);
    const delta = max - min;
    const l = (max + min) / 2;

    let h = 0;
    let s = 0;
    if (delta !== 0) {
      s = delta / (1 - Math.abs(2 * l - 1));
      switch (max) {
        case red: h = ((green - blue) / delta) % 6; break;
        case green: h = (blue - red) / delta + 2; break;
        default: h = (red - green) / delta + 4; break;
      }
      h *= 60;
      if (h < 0) h += 360;
    }

    return { h, s, l };
  };

  const colorNameFromHex = hex => {
    const rgb = hex.replace("#", "");
    const [r, g, b] = [0, 2, 4].map(index => Number.parseInt(rgb.slice(index, index + 2), 16));
    const { h, s, l } = rgbToHsl(r, g, b);

    if (s < 0.18 && l > 0.7) return "Beige claro";
    if (s < 0.18 && l < 0.35) return "Marrón oscuro";
    if (h >= 330 || h < 20) return "Terracota";
    if (h >= 20 && h < 50) return "Marrón cálido";
    if (h >= 50 && h < 90) return "Mostaza / verde oliva";
    if (h >= 90 && h < 160) return "Verde natural";
    if (h >= 160 && h < 220) return "Azul / verde frío";
    if (h >= 220 && h < 290) return "Morado / lavanda";
    return "Rosa / rubor";
  };

  const updateSizeSummary = () => {
    const enteredMeasures = [
      ["busto", "bust", "Busto", "Bust"],
      ["cintura", "waist", "Cintura", "Waist"],
      ["cadera", "hip", "Cadera", "Hip"],
    ].flatMap(([measure, fieldName, label, rangeKey]) => {
      const field = wizardForm.querySelector(`[name="${fieldName}"]`);
      const value = Number.parseFloat(field?.value.replace(",", ".") ?? "");
      return Number.isFinite(value) && value > 0
        ? [{ measure, value, label, rangeKey }]
        : [];
    });

    sizeSummaryMeasures.replaceChildren(...enteredMeasures.map(({ label, value }) => {
      const item = document.createElement("li");
      item.textContent = `${label}: ${new Intl.NumberFormat("es-CL", {
        maximumFractionDigits: 1,
      }).format(value)} cm`;
      return item;
    }));
    sizeSummarySizes.replaceChildren();

    if (!enteredMeasures.length) {
      sizeSummaryStatus.textContent = "Completa tus medidas para consultar tallas compatibles o cercanas.";
      return;
    }

    const rows = Array.from(document.querySelectorAll(".size-chart tbody tr"))
      .filter(row => row.querySelector("[data-standard-size]"));
    const rangesFor = row => enteredMeasures.map(({ value, rangeKey }) => {
      const cell = row.querySelector("[data-standard-size]");
      const minimum = Number(cell?.dataset[`size${rangeKey}Min`]);
      const maximum = Number(cell?.dataset[`size${rangeKey}Max`]);
      return {
        compatible: value >= minimum && value <= maximum,
        distance: Math.max(minimum - value, value - maximum, 0),
      };
    });
    const exactRows = rows.filter(row => rangesFor(row).every(range => range.compatible));
    const closestRows = exactRows.length
      ? exactRows
      : rows.filter(row => {
        const distance = rangesFor(row).reduce((total, range) => total + range.distance, 0);
        const minimumDistance = Math.min(
          ...rows.map(candidate => rangesFor(candidate)
            .reduce((total, range) => total + range.distance, 0)),
        );
        return Math.abs(distance - minimumDistance) < 1e-9;
      });

    if (!closestRows.length) {
      sizeSummaryStatus.textContent = "No se pudo consultar la tabla estándar de tallas.";
      return;
    }

    sizeSummaryStatus.textContent = exactRows.length
      ? "Tallas compatibles con las medidas ingresadas:"
      : "Tallas más cercanas; tus medidas no coinciden todas con un mismo rango:";
    closestRows.forEach(row => {
      const cells = row.querySelectorAll("th, td");
      const size = document.createElement("span");
      size.className = "wizard-summary-size";
      size.textContent = [
        cells[0]?.textContent.trim(),
        cells[1]?.textContent.trim() && `EU ${cells[1].textContent.trim()}`,
        cells[2]?.textContent.trim() && `EE. UU. ${cells[2].textContent.trim()}`,
      ].filter(Boolean).join(" · ");
      sizeSummarySizes.append(size);
    });
  };

  const applyAnalysis = palette => {
    currentPalette = palette;
    const average = palette.reduce((sum, item) => {
      const [r, g, b] = item.rgb;
      const { h, s, l } = rgbToHsl(r, g, b);
      sum.h += h;
      sum.s += s;
      sum.l += l;
      return sum;
    }, { h: 0, s: 0, l: 0 });

    const averageH = average.h / palette.length;
    const averageL = average.l / palette.length;
    const imageDepth = averageL < 0.32 ? "Muy profundo" : averageL < 0.5 ? "Profundo" : averageL < 0.68 ? "Medio" : "Claro";
    const undertone = averageH >= 330 || averageH < 30
      ? "Cálido"
      : averageH >= 30 && averageH < 200
        ? "Neutro"
        : "Frío";

    paletteSummaryStatus.textContent = `Subtono ${undertone.toLowerCase()} · profundidad ${imageDepth.toLowerCase()}. La iluminación, el fondo y la ropa pueden influir en el resultado.`;
    paletteSummaryColors.replaceChildren(...palette.map(item => {
      const color = document.createElement("span");
      const swatch = document.createElement("span");
      const label = document.createElement("span");
      const name = colorNameFromHex(item.hex);
      color.className = "wizard-summary-color";
      swatch.className = "wizard-summary-color-swatch";
      swatch.style.backgroundColor = item.hex;
      label.textContent = name;
      color.append(swatch, label);
      return color;
    }));
    try {
      sessionStorage.setItem(paletteStorageKey, JSON.stringify(palette));
    } catch (error) {
      console.error("No se pudo conservar la paleta durante la sesión.", error);
    }
    window.dispatchEvent(new CustomEvent("matices:palette-updated", {
      detail: { palette },
    }));
  };

  const analyzeSelectedImage = () => new Promise(resolve => {
    const file = selectedPhoto;
    if (!file || !file.type.startsWith("image/")) {
      setStatus("Sube una foto para analizar tu paleta.");
      resolve(false);
      return;
    }

    const image = new Image();
    image.decoding = "async";
    const reader = new FileReader();

    reader.onload = () => {
      setStatus("Analizando tonos y profundidad...");
      image.onload = () => {
        try {
          const canvas = document.createElement("canvas");
          const maxDimension = 220;
          const scale = Math.min(maxDimension / image.width, maxDimension / image.height, 1);
          canvas.width = Math.max(1, Math.round(image.width * scale));
          canvas.height = Math.max(1, Math.round(image.height * scale));
          const context = canvas.getContext("2d");
          if (!context) throw new Error("No se pudo preparar el análisis de la foto.");
          context.drawImage(image, 0, 0, canvas.width, canvas.height);

          const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
          const buckets = new Map();

          for (let i = 0; i < data.length; i += 4) {
            const alpha = data[i + 3];
            if (alpha < 180) continue;
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            const luminance = (r * 0.299) + (g * 0.587) + (b * 0.114);
            if (luminance < 20 || luminance > 245) continue;
            const key = `${Math.round(r / 24) * 24}-${Math.round(g / 24) * 24}-${Math.round(b / 24) * 24}`;
            buckets.set(key, (buckets.get(key) || 0) + 1);
          }

          const palette = [...buckets.entries()]
            .sort((a, b) => b[1] - a[1])
            .slice(0, 5)
            .map(([key, count]) => {
              const [r, g, b] = key.split("-").map(Number);
              return { rgb: [r, g, b], hex: `#${rgbToHex(r, g, b)}`, count };
            });

          if (!palette.length) {
            setStatus("No se pudo detectar una paleta clara. Prueba con otra imagen.");
            resolve(false);
            return;
          }

          applyAnalysis(palette);
          setStatus("Análisis listo. Revisa el resumen de paleta y medidas.");
          resolve(true);
        } catch (error) {
          setStatus("No se pudo analizar la foto. Intenta con otra imagen.");
          console.error("No se pudo analizar la foto.", error);
          resolve(false);
        }
      };
      image.onerror = () => {
        setStatus("No se pudo abrir la foto. Selecciona otra imagen.");
        resolve(false);
      };
      image.src = reader.result;
    };
    reader.onerror = () => {
      setStatus("No se pudo leer la foto. Intenta seleccionarla nuevamente.");
      resolve(false);
    };
    reader.readAsDataURL(file);
  });

  fileInput?.addEventListener("change", () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    stopCamera();
    showSelectedPhoto(file);
  });
  removePhotoButton?.addEventListener("click", removeSelectedPhoto);
  cameraButton?.addEventListener("click", async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setStatus("La cámara requiere un navegador compatible y una conexión segura (HTTPS o localhost). Puedes elegir una foto del dispositivo.");
      return;
    }

    cameraButton.disabled = true;
    setStatus("Solicitando permiso para usar la cámara...");
    try {
      cameraStream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: "user" },
      });
      cameraVideo.srcObject = cameraStream;
      cameraPanel.hidden = false;
      await cameraVideo.play();
      setStatus("Encuadra tu rostro y presiona Capturar foto.");
    } catch (error) {
      stopCamera();
      if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
        setStatus("No se concedió permiso para usar la cámara. Autoriza el acceso en el navegador o elige una foto del dispositivo.");
      } else if (error.name === "NotFoundError" || error.name === "DevicesNotFoundError") {
        setStatus("No se encontró una cámara disponible. Puedes elegir una foto del dispositivo.");
      } else {
        setStatus("No se pudo iniciar la cámara. Revisa los permisos o elige una foto del dispositivo.");
        console.error("No se pudo iniciar la cámara.", error);
      }
    }
  });

  captureButton?.addEventListener("click", () => {
    if (!cameraStream || !cameraVideo.videoWidth || !cameraVideo.videoHeight) {
      setStatus("La cámara aún no está lista. Espera un momento e inténtalo nuevamente.");
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = cameraVideo.videoWidth;
    canvas.height = cameraVideo.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      setStatus("No se pudo capturar la foto. Puedes elegir una imagen del dispositivo.");
      return;
    }
    context.translate(canvas.width, 0);
    context.scale(-1, 1);
    context.drawImage(cameraVideo, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(blob => {
      if (!blob) {
        setStatus("No se pudo guardar la foto capturada. Inténtalo nuevamente.");
        return;
      }
      stopCamera();
      showSelectedPhoto(new File([blob], "foto-camara.jpg", { type: "image/jpeg" }));
    }, "image/jpeg", 0.92);
  });

  cancelCameraButton?.addEventListener("click", () => {
    stopCamera();
    setStatus(selectedPhoto
      ? "Se conserva la foto seleccionada. Puedes usarla o elegir otra."
      : "Cámara cerrada. Puedes tomar otra foto o elegir una del dispositivo.");
  });

  nextButton?.addEventListener("click", async () => {
    nextButton.disabled = true;
    const analyzed = await analyzeSelectedImage();
    nextButton.disabled = !selectedPhoto;
    if (analyzed) showStep(2);
  });
  wizard.querySelectorAll("[data-wizard-next]").forEach(button => {
    button.addEventListener("click", () => {
      showStep(Number(button.dataset.wizardNext));
    });
  });
  wizard.querySelectorAll("[data-wizard-back]").forEach(button => {
    button.addEventListener("click", () => {
      const activePanel = button.closest("[data-wizard-panel]");
      showStep(Number(activePanel.dataset.wizardPanel) - 1);
    });
  });

  rememberBox?.addEventListener("change", async () => {
    if (!rememberStatus) return;
    window.dispatchEvent(new CustomEvent("matices:photo-remember-changed", {
      detail: {
        enabled: rememberBox.checked,
        file: rememberBox.checked ? selectedPhoto : null,
      },
    }));
    if (rememberBox.checked) {
      try {
        localStorage.setItem(rememberedPhotoEnabledKey, "true");
        if (selectedPhoto) {
          await persistSelectedPhoto(selectedPhoto, false);
        } else {
          rememberStatus.textContent = "La próxima foto se guardará en este navegador.";
        }
      } catch (error) {
        rememberStatus.textContent = "No se pudo activar el recuerdo de la foto.";
        console.error("No se pudo activar el recuerdo de la foto.", error);
      }
      return;
    }

    try {
      localStorage.removeItem(rememberedPhotoEnabledKey);
      await deleteRememberedPhoto();
      rememberStatus.textContent = "La foto guardada se eliminó de este navegador.";
    } catch (error) {
      rememberStatus.textContent = "No se pudo eliminar la foto guardada.";
      console.error("No se pudo desactivar el recuerdo de la foto.", error);
    }
  });

  window.addEventListener("matices:restore-photo", event => {
    const file = event.detail?.file;
    if (!(file instanceof File)) return;
    rememberBox.checked = true;
    try {
      localStorage.setItem(rememberedPhotoEnabledKey, "true");
    } catch (error) {
      rememberStatus.textContent = "Foto recuperada de tu cuenta, pero no se pudo recordar en este navegador.";
      console.error("No se pudo guardar la preferencia local de la foto.", error);
    }
    saveRememberedPhoto(file)
      .then(() => {
        showSelectedPhoto(file, false, false);
        rememberStatus.textContent = "Foto recuperada de tu cuenta y guardada en este navegador.";
      })
      .catch(error => {
        showSelectedPhoto(file, false, false);
        rememberStatus.textContent = "Foto recuperada de tu cuenta, pero no se pudo guardar en este navegador.";
        console.error("No se pudo conservar localmente la foto de la cuenta.", error);
      });
  });

  wizardForm?.querySelectorAll(".measurement-input").forEach(field => {
    field.addEventListener("input", updateSizeSummary);
  });

  let preparingWizardSubmission = false;
  let resubmittingWizardForm = false;
  wizardForm?.addEventListener("submit", async event => {
    if (resubmittingWizardForm) {
      resubmittingWizardForm = false;
      if (stepInput) stepInput.value = "3";
      try {
        sessionStorage.setItem(paletteStorageKey, JSON.stringify(currentPalette));
      } catch (error) {
        console.error("No se pudo conservar la paleta durante la sesión.", error);
      }
      return;
    }

    event.preventDefault();
    if (preparingWizardSubmission) return;
    preparingWizardSubmission = true;
    const submitter = event.submitter;
    const photoSaved = await tryOnPhotoSavePromise;
    if (!photoSaved && rememberStatus) {
      rememberStatus.textContent = "La foto no se conservará al navegar al catálogo; vuelve a Inicio para probarla.";
    }
    try {
      resubmittingWizardForm = true;
      if (submitter) wizardForm.requestSubmit(submitter);
      else wizardForm.requestSubmit();
    } catch (error) {
      resubmittingWizardForm = false;
      setStatus("No se pudo continuar al catálogo. Inténtalo nuevamente.");
      console.error("No se pudo enviar el formulario del asistente.", error);
    } finally {
      preparingWizardSubmission = false;
    }
  });

  window.addEventListener("matices:restore-palette", event => {
    const palette = event.detail?.palette;
    if (Array.isArray(palette) && palette.length === 0) {
      currentPalette = [];
      paletteSummaryStatus.textContent = "Completa el análisis de la foto para ver tu paleta.";
      paletteSummaryColors.replaceChildren();
      try {
        sessionStorage.setItem(paletteStorageKey, "[]");
      } catch (error) {
        console.error("No se pudo limpiar la paleta recuperada.", error);
      }
      return;
    }
    if (
      Array.isArray(palette)
      && palette.length > 0
      && palette.every(item =>
        typeof item?.hex === "string"
        && Array.isArray(item.rgb)
        && item.rgb.length === 3
        && item.rgb.every(Number.isFinite)
      )
    ) {
      applyAnalysis(palette);
    }
  });

  try {
    const storedPalette = JSON.parse(sessionStorage.getItem(paletteStorageKey) || "[]");
    if (
      Array.isArray(storedPalette)
      && storedPalette.length > 0
      && storedPalette.every(item =>
        typeof item?.hex === "string"
        && Array.isArray(item.rgb)
        && item.rgb.length === 3
        && item.rgb.every(Number.isFinite)
      )
    ) {
      applyAnalysis(storedPalette);
    }
  } catch (error) {
    console.error("No se pudo recuperar la paleta de esta sesión.", error);
  }

  const requestedStep = Number(stepInput?.value);
  const initialStep = requestedStep === 2 || (requestedStep === 3 && currentPalette.length)
    ? Math.min(requestedStep, panels.length)
    : 1;
  updateSizeSummary();
  showStep(initialStep);
  if (new URLSearchParams(window.location.search).get("view") === "account") {
    showAccount();
  }
  cleanExpiredTryOnPhotos()
    .then(loadTryOnPhotoForSession)
    .then(savedPhoto => {
      if (!savedPhoto?.blob) return;
      if (savedPhoto.expiresAt <= Date.now()) {
        return removeTryOnPhotoForSession();
      }
      const file = new File([savedPhoto.blob], savedPhoto.name || "foto-de-inicio", {
        type: savedPhoto.type || savedPhoto.blob.type || "image/jpeg",
        lastModified: savedPhoto.lastModified || Date.now(),
      });
      showSelectedPhoto(file, false, false);
    })
    .catch(error => {
      console.error("No se pudo recuperar la foto para el Probador.", error);
    });
  restoreRememberedPhoto();
  window.addEventListener("pagehide", stopCamera);
})();

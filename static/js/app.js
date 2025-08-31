// ===== CONFIGURAÇÕES GLOBAIS =====
document.addEventListener("DOMContentLoaded", () => {
  // Import Bootstrap
  const bootstrap = window.bootstrap

  // Inicializa tooltips do Bootstrap
  var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'))
  var tooltipList = tooltipTriggerList.map((tooltipTriggerEl) => new bootstrap.Tooltip(tooltipTriggerEl))

  // Inicializa popovers do Bootstrap
  var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'))
  var popoverList = popoverTriggerList.map((popoverTriggerEl) => new bootstrap.Popover(popoverTriggerEl))

  // Auto-hide alerts após 5 segundos
  setTimeout(() => {
    const alerts = document.querySelectorAll(".alert")
    alerts.forEach((alert) => {
      const bsAlert = new bootstrap.Alert(alert)
      bsAlert.close()
    })
  }, 5000)

  // Adiciona animações aos elementos
  addScrollAnimations()

  // Inicializa componentes personalizados
  initCustomComponents()
})

// ===== ANIMAÇÕES DE SCROLL =====
function addScrollAnimations() {
  const observerOptions = {
    threshold: 0.1,
    rootMargin: "0px 0px -50px 0px",
  }

  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("fade-in")
      }
    })
  }, observerOptions)

  // Observa elementos que devem ter animação
  const animatedElements = document.querySelectorAll(".card, .alert, .auth-card")
  animatedElements.forEach((el) => {
    observer.observe(el)
  })
}

// ===== COMPONENTES PERSONALIZADOS =====
function initCustomComponents() {
  // Loading states para formulários
  const forms = document.querySelectorAll("form")
  forms.forEach((form) => {
    form.addEventListener("submit", (e) => {
      const submitBtn = form.querySelector('button[type="submit"]')
      if (submitBtn && !submitBtn.disabled) {
        const originalText = submitBtn.innerHTML
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-2"></i>Processando...'
        submitBtn.disabled = true

        // Restaura o botão após 10 segundos (fallback)
        setTimeout(() => {
          submitBtn.innerHTML = originalText
          submitBtn.disabled = false
        }, 10000)
      }
    })
  })

  // Validação em tempo real para campos de email
  const emailInputs = document.querySelectorAll('input[type="email"]')
  emailInputs.forEach((input) => {
    input.addEventListener("blur", function () {
      validateEmail(this)
    })
  })

  // Validação em tempo real para senhas
  const passwordInputs = document.querySelectorAll('input[type="password"]')
  passwordInputs.forEach((input) => {
    if (input.name === "password") {
      input.addEventListener("input", function () {
        validatePassword(this)
      })
    }
  })
}

// ===== VALIDAÇÕES =====
function validateEmail(input) {
  const email = input.value.trim()
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

  if (email && !emailRegex.test(email)) {
    input.classList.add("is-invalid")
    input.classList.remove("is-valid")
    showFieldError(input, "Email inválido")
  } else if (email) {
    input.classList.add("is-valid")
    input.classList.remove("is-invalid")
    hideFieldError(input)
  } else {
    input.classList.remove("is-valid", "is-invalid")
    hideFieldError(input)
  }
}

function validatePassword(input) {
  const password = input.value
  const minLength = 6

  let isValid = true
  const errors = []

  if (password.length < minLength) {
    isValid = false
    errors.push(`Mínimo ${minLength} caracteres`)
  }

  if (!/[A-Za-z]/.test(password)) {
    isValid = false
    errors.push("Pelo menos uma letra")
  }

  if (!/\d/.test(password)) {
    isValid = false
    errors.push("Pelo menos um número")
  }

  if (password.length > 0) {
    if (isValid) {
      input.classList.add("is-valid")
      input.classList.remove("is-invalid")
      hideFieldError(input)
    } else {
      input.classList.add("is-invalid")
      input.classList.remove("is-valid")
      showFieldError(input, errors.join(", "))
    }
  } else {
    input.classList.remove("is-valid", "is-invalid")
    hideFieldError(input)
  }
}

function showFieldError(input, message) {
  hideFieldError(input) // Remove erro anterior

  const errorDiv = document.createElement("div")
  errorDiv.className = "invalid-feedback"
  errorDiv.textContent = message
  errorDiv.setAttribute("data-field-error", input.name)

  input.parentNode.appendChild(errorDiv)
}

function hideFieldError(input) {
  const existingError = input.parentNode.querySelector(`[data-field-error="${input.name}"]`)
  if (existingError) {
    existingError.remove()
  }
}

// ===== UTILITÁRIOS =====
function showNotification(message, type = "info", duration = 5000) {
  const alertDiv = document.createElement("div")
  alertDiv.className = `alert alert-${type} alert-dismissible fade show`
  alertDiv.innerHTML = `
        <i class="fas fa-info-circle me-2"></i>
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `

  // Adiciona ao container de notificações ou ao topo da página
  const container = document.querySelector(".container") || document.body
  container.insertBefore(alertDiv, container.firstChild)

  // Remove automaticamente após o tempo especificado
  setTimeout(() => {
    const bsAlert = new window.bootstrap.Alert(alertDiv)
    bsAlert.close()
  }, duration)
}

function formatCurrency(value) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value)
}

function formatDate(dateString) {
  const date = new Date(dateString)
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}

function debounce(func, wait) {
  let timeout
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout)
      func(...args)
    }
    clearTimeout(timeout)
    timeout = setTimeout(later, wait)
  }
}

// ===== TOGGLE DE SENHA =====
function togglePassword(fieldId) {
  const field = document.getElementById(fieldId)
  const eye = document.getElementById(fieldId + "-eye")

  if (field && eye) {
    if (field.type === "password") {
      field.type = "text"
      eye.className = "fas fa-eye-slash"
    } else {
      field.type = "password"
      eye.className = "fas fa-eye"
    }
  }
}

// ===== LOADING OVERLAY =====
function showLoadingOverlay(message = "Carregando...") {
  const overlay = document.createElement("div")
  overlay.id = "loadingOverlay"
  overlay.className = "loading-overlay"
  overlay.innerHTML = `
        <div class="loading-content">
            <div class="spinner-border text-primary mb-3" role="status">
                <span class="visually-hidden">Carregando...</span>
            </div>
            <p class="mb-0">${message}</p>
        </div>
    `

  document.body.appendChild(overlay)

  // Adiciona estilos se não existirem
  if (!document.querySelector("#loadingOverlayStyles")) {
    const styles = document.createElement("style")
    styles.id = "loadingOverlayStyles"
    styles.textContent = `
            .loading-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 9999;
                backdrop-filter: blur(5px);
            }
            .loading-content {
                background: white;
                padding: 2rem;
                border-radius: 12px;
                text-align: center;
                box-shadow: 0 8px 25px rgba(0, 0, 0, 0.2);
            }
        `
    document.head.appendChild(styles)
  }
}

function hideLoadingOverlay() {
  const overlay = document.getElementById("loadingOverlay")
  if (overlay) {
    overlay.remove()
  }
}

// ===== EXPORTA FUNÇÕES GLOBAIS =====
window.togglePassword = togglePassword
window.showNotification = showNotification
window.showLoadingOverlay = showLoadingOverlay
window.hideLoadingOverlay = hideLoadingOverlay
window.formatCurrency = formatCurrency
window.formatDate = formatDate

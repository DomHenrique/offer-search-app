// image-loader.js
// Script para lidar com o carregamento de imagens e fallback

document.addEventListener('DOMContentLoaded', function() {
    // Trata o carregamento de imagens com fallback
    handleImageLoading();
});

function handleImageLoading() {
    // Observa imagens que entram na viewport
    const imageObserver = new IntersectionObserver((entries, observer) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                loadImage(img);
                observer.unobserve(img);
            }
        });
    }, {
        rootMargin: '50px' // Começa a carregar antes de entrar na viewport
    });

    // Observa todas as imagens de produtos
    const productImages = document.querySelectorAll('.product-image img, .card-img-top');
    productImages.forEach(img => {
        imageObserver.observe(img);
    });
}

function loadImage(img) {
    // Se já tem src válido, não faz nada
    if (img.src && !img.src.includes('no-image')) {
        return;
    }

    // Adiciona evento de erro para fallback
    img.addEventListener('error', function() {
        console.log('Erro ao carregar imagem, usando fallback');
        this.src = '/static/img/no-image.png';
        this.classList.add('image-error');
    });

    // Se tem data-src, carrega a imagem
    if (img.dataset.src) {
        img.src = img.dataset.src;
    }
}

// Adiciona animação suave para imagens que estão carregando
function addImageLoadingAnimation() {
    const style = document.createElement('style');
    style.textContent = `
        .product-image {
            position: relative;
            background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
            background-size: 200% 100%;
            animation: loading 1.5s infinite;
        }
        
        @keyframes loading {
            0% {
                background-position: 200% 0;
            }
            100% {
                background-position: -200% 0;
            }
        }
        
        .product-image img {
            transition: opacity 0.3s ease;
        }
        
        .product-image img.loading {
            opacity: 0.7;
        }
        
        .product-image img.loaded {
            opacity: 1;
        }
        
        .image-error {
            opacity: 0.5;
            filter: grayscale(100%);
        }
    `;
    document.head.appendChild(style);
}

// Chama a função para adicionar animações
addImageLoadingAnimation();

// Exporta funções globais
window.handleImageLoading = handleImageLoading;
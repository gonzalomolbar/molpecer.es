// Configuration
const CONFIG = {
    particles: {
        count: 190,          // Number of particles
        minSize: 0.5,        // Minimum particle size
        maxSize: 2.0,        // Maximum particle size (base size + random)
        fadeInSpeed: 0.02,   // How fast particles fade in
        minAmplitude: 30,    // Minimum movement amplitude
        maxAmplitude: 60,    // Maximum movement amplitude (base + random)
        speed: 0.2,          // Particle movement speed
        large: {
            count: 10,       // Number of large particles
            scale: 2.0       // Size multiplier for large particles
        }
    },
    interaction: {
        attractionRadius: 400,     // How far particles react to mouse/touch
        attractionStrength: 2.0,   // How strongly particles are attracted
        moveMultiplier: 1.5        // Movement speed when attracted
    }
};

// Add this at the start, before creating the canvas
function setVHProperty() {
    // First we get the viewport height and we multiply it by 1% to get a value for a vh unit
    let vh = window.innerHeight * 0.01;
    // Then we set the value in the --vh custom property to the root of the document
    document.documentElement.style.setProperty('--vh', `${vh}px`);
}

// Initial set
setVHProperty();

// Create canvas for particles (background)
const particleCanvas = document.createElement('canvas');
particleCanvas.style.position = 'fixed';
particleCanvas.style.top = '0';
particleCanvas.style.left = '0';
particleCanvas.style.width = '100%';
particleCanvas.style.height = '100%';
particleCanvas.style.zIndex = '0';  // Set to 0 to be behind the sections
document.body.prepend(particleCanvas);

// Add event overlay for capturing touches
const eventOverlay = document.getElementById('eventOverlay');

// Add container z-index
const container = document.querySelector('.container');
container.style.position = 'relative';
container.style.zIndex = '2';  // Above canvas

const ctx = particleCanvas.getContext('2d');
const particles = [];
const mouse = { x: null, y: null, clicking: false };

// Global variable to track if the click started in a section
let clickStartedOutsideSection = false;

// Single function to handle all input
function handleInput(e) {
    // Check if the click started within a section
    if (e.type === 'mousedown' || e.type === 'touchstart') {
        // Log the target element for debugging
        clickStartedOutsideSection = e.target.closest('.section') === null;
    }

    if (clickStartedOutsideSection) {
        // Allow text selection by default
        document.body.style.userSelect = 'none'; // Prevent text selection
    } else {
        document.body.style.userSelect = 'auto'; // Allow text selection
    }

    // Handle release events
    if (e.type === 'mouseup' || e.type === 'touchend' || e.type === 'mouseleave') {
        mouse.clicking = false;
        mouse.x = null;
        mouse.y = null;
        document.body.style.userSelect = 'auto'; // Re-enable text selection
        clickStartedOutsideSection = false; // Reset the flag
        return;
    }

    // Get coordinates
    let x, y;
    if (e.touches) {
        x = e.touches[0].pageX - window.scrollX;
        y = e.touches[0].pageY - window.scrollY;
    } else {
        x = e.pageX - window.scrollX;
        y = e.pageY - window.scrollY;
    }

    const scale = particleCanvas.height / window.innerHeight;
    y = y * scale;

    mouse.x = x;
    mouse.y = y;

    if (e.type === 'mousedown' || e.type === 'touchstart') {
        mouse.clicking = true;
    }
}

// Add event listeners back to document
document.addEventListener('mousemove', handleInput);
document.addEventListener('mousedown', handleInput);
document.addEventListener('mouseup', handleInput);
document.addEventListener('mouseleave', handleInput);
document.addEventListener('touchstart', handleInput, { passive: true });
document.addEventListener('touchmove', handleInput, { passive: true });
document.addEventListener('touchend', handleInput);

class Particle {
    constructor(canvas) {
        this.canvas = canvas;
        this.originalX = Math.random() * canvas.width;
        this.originalY = Math.random() * canvas.height;
        this.x = this.originalX;
        this.y = this.originalY;
        this.size = Math.random() * (CONFIG.particles.maxSize - CONFIG.particles.minSize) + CONFIG.particles.minSize;
        
        this.time = 0;
        this.speed = CONFIG.particles.speed;
        this.amplitude = CONFIG.particles.minAmplitude + Math.random() * (CONFIG.particles.maxAmplitude - CONFIG.particles.minAmplitude);
        this.angleX = Math.random() * Math.PI * 2;
        this.angleY = Math.random() * Math.PI * 2;
        
        this.opacity = 0; // Start invisible
        
        this.attractionRadius = CONFIG.interaction.attractionRadius;
        this.attractionStrength = CONFIG.interaction.attractionStrength;
    }

    update(mouse) {
        // Fade in opacity and movement
        if (this.opacity < 1) {
            this.opacity += CONFIG.particles.fadeInSpeed;
        }
        const fadeInProgress = this.opacity;
        const currentAmplitude = this.amplitude * fadeInProgress;

        if (mouse.clicking && mouse.x !== null && mouse.y !== null) {
            const dx = mouse.x - this.x;
            const dy = mouse.y - this.y;
            const distance = Math.sqrt(dx * dx + dy * dy);

            if (distance > 0 && distance < this.attractionRadius) {
                const force = (1 - distance / this.attractionRadius) * this.attractionStrength;
                this.x += (dx / distance) * force * CONFIG.interaction.moveMultiplier;
                this.y += (dy / distance) * force * CONFIG.interaction.moveMultiplier;
            }
        } else {
            this.time += this.speed;
            
            const targetX = this.originalX + Math.cos(this.angleX + this.time * 0.01) * currentAmplitude;
            const targetY = this.originalY + Math.sin(this.angleY + this.time * 0.01) * currentAmplitude;
            
            this.x += (targetX - this.x) * 0.05;
            this.y += (targetY - this.y) * 0.05;
        }

        // Keep particles within bounds and update original position when wrapping
        if (this.x < 0) {
            this.x = this.canvas.width;
            this.originalX = this.x;
        }
        if (this.x > this.canvas.width) {
            this.x = 0;
            this.originalX = this.x;
        }
        if (this.y < 0) {
            this.y = this.canvas.height;
            this.originalY = this.y;
        }
        if (this.y > this.canvas.height) {
            this.y = 0;
            this.originalY = this.y;
        }
    }

    draw(ctx) {
        ctx.beginPath();
        const gradient = ctx.createRadialGradient(this.x, this.y, 0, this.x, this.y, this.size * 2);
        gradient.addColorStop(0, `rgba(255, 255, 255, ${this.opacity * 0.8})`);
        gradient.addColorStop(1, 'rgba(255, 255, 255, 0)');
        ctx.fillStyle = gradient;
        ctx.arc(this.x, this.y, this.size * 2, 0, Math.PI * 2);
        ctx.fill();
    }
}

function resizeCanvas() {
    // Make canvas 20% taller than viewport to account for mobile UI
    particleCanvas.width = window.innerWidth;
    particleCanvas.height = window.innerHeight * 1.2;

    // Only initialize particles on first resize
    if (particles.length === 0) {
        init();
    }
}

function init() {
    particles.length = 0;
    
    // Regular particles
    for (let i = 0; i < CONFIG.particles.count; i++) {
        particles.push(new Particle(particleCanvas));
    }
    
    // Add large particles
    for (let i = 0; i < CONFIG.particles.large.count; i++) {
        const largeParticle = new Particle(particleCanvas);
        largeParticle.size = largeParticle.size * CONFIG.particles.large.scale;
        particles.push(largeParticle);
    }
}

function animate() {
    ctx.clearRect(0, 0, particleCanvas.width, particleCanvas.height);
    particles.forEach(particle => {
        particle.update(mouse);
        particle.draw(ctx);
    });
    requestAnimationFrame(animate);
}

// Remove all the vh property related code
// Remove debounce
window.addEventListener('resize', resizeCanvas);

resizeCanvas();
init();
animate(); 
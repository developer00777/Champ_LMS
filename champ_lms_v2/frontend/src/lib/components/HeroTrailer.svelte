<script lang="ts">
  import type { Module } from '$lib/api/client';
  export let module: Module | null = null;
</script>

{#if module}
  <div class="hero">
    <!-- Background with fallback gradient when no thumbnail -->
    <div class="hero-bg" style="background-image: url({module.thumbnail_url || ''})"></div>
    <div class="hero-overlay"></div>
    
    <div class="hero-content">
      {#if module.category}
        <span class="badge badge-category">{module.category}</span>
      {/if}
      <h1>{module.title}</h1>
      {#if module.description}
        <p class="desc">{module.description}</p>
      {:else}
        <p class="desc">Start learning with this module.</p>
      {/if}
      <div class="hero-actions">
        <a href="/module/{module.id}" class="btn-primary">
          <span class="play-icon">▶</span> Play
        </a>
        <a href="/module/{module.id}" class="btn-ghost">More Info</a>
      </div>
    </div>
  </div>
{:else}
  <!-- Empty hero state -->
  <div class="hero hero-empty">
    <div class="hero-content">
      <h1>Welcome to Champ LMS</h1>
      <p class="desc">Start your learning journey today.</p>
      <div class="hero-actions">
        <a href="/admin/upload" class="btn-primary">Upload First Video</a>
      </div>
    </div>
  </div>
{/if}

<style>
  .hero {
    position: relative;
    width: 100%;
    min-height: 450px;
    display: flex;
    align-items: flex-end;
    margin-bottom: 3rem;
    border-radius: 16px;
    overflow: hidden;
    background: linear-gradient(135deg, var(--surface) 0%, var(--surface2) 100%);
  }
  
  .hero-bg {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-size: cover;
    background-position: center;
    background-repeat: no-repeat;
    transition: transform 0.3s ease;
  }
  
  .hero:hover .hero-bg {
    transform: scale(1.02);
  }
  
  .hero-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: linear-gradient(
      to top,
      var(--bg) 0%,
      rgba(10, 10, 15, 0.8) 40%,
      rgba(10, 10, 15, 0.3) 70%,
      transparent 100%
    );
    background: linear-gradient(
      to right,
      var(--bg) 0%,
      rgba(10, 10, 15, 0.9) 30%,
      rgba(10, 10, 15, 0.6) 60%,
      rgba(10, 10, 15, 0.2) 100%
    );
  }
  
  .hero-content {
    position: relative;
    z-index: 2;
    padding: 3rem 2.5rem;
    max-width: 600px;
  }
  
  h1 {
    font-size: 2.5rem;
    font-weight: 800;
    line-height: 1.1;
    margin: 0.75rem 0;
    text-shadow: 0 2px 12px rgba(0,0,0,0.5);
    letter-spacing: -0.02em;
  }
  
  .desc {
    color: var(--muted);
    font-size: 1rem;
    line-height: 1.6;
    margin-bottom: 1.5rem;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    max-width: 480px;
  }
  
  .hero-actions {
    display: flex;
    gap: 1rem;
    align-items: center;
  }
  
  .play-icon {
    margin-right: 0.4rem;
    font-size: 0.8em;
  }
  
  .btn-primary, .btn-ghost {
    padding: 0.7rem 1.8rem;
    font-size: 1rem;
  }
  
  /* Empty state */
  .hero-empty {
    background: linear-gradient(135deg, var(--surface) 0%, var(--surface2) 50%, var(--surface) 100%);
    background-size: 200% 200%;
    animation: gradientShift 8s ease infinite;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
  }
  
  .hero-empty .hero-content {
    max-width: 500px;
    padding: 4rem 2rem;
  }
  
  @keyframes gradientShift {
    0%, 100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
  }
  
  @media (max-width: 768px) {
    .hero {
      min-height: 350px;
    }
    h1 {
      font-size: 1.8rem;
    }
    .hero-content {
      padding: 2rem 1.5rem;
    }
  }
</style>

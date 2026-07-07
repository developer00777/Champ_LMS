<script lang="ts">
  import type { Module } from '$lib/api/client';
  export let module: Module;
  export let progress: number = 0; // 0-100

  // Generate a gradient placeholder based on module title (consistent color)
  function getGradient(title: string) {
    const gradients = [
      'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
      'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
      'linear-gradient(135deg, #43e97b 0%, #38f9d7 100%)',
      'linear-gradient(135deg, #fa709a 0%, #fee140 100%)',
      'linear-gradient(135deg, #30cfd0 0%, #330867 100%)',
      'linear-gradient(135deg, #a8edea 0%, #fed6e3 100%)',
      'linear-gradient(135deg, #ff9a9e 0%, #fecfef 100%)',
    ];
    let hash = 0;
    for (let i = 0; i < title.length; i++) {
      hash = title.charCodeAt(i) + ((hash << 5) - hash);
    }
    return gradients[Math.abs(hash) % gradients.length];
  }

  $: hasThumbnail = !!module.thumbnail_url && module.thumbnail_url !== '/placeholder-thumb.svg';
  $: gradientStyle = !hasThumbnail ? getGradient(module.title) : '';
</script>

<a href="/module/{module.id}" class="card">
  <div class="thumb-wrap" style={!hasThumbnail ? `background: ${gradientStyle}` : ''}>
    {#if hasThumbnail}
      <img 
        src={module.thumbnail_url} 
        alt={module.title} 
        class="thumb" 
        loading="lazy"
        on:error={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
      />
    {:else}
      <div class="thumb-placeholder">
        <span class="thumb-icon">▶</span>
      </div>
    {/if}
    
    {#if progress > 0}
      <div class="progress-bar-container">
        <div class="progress-bar" style="width:{progress}%"></div>
      </div>
    {/if}
    
    {#if module.total_episodes > 1}
      <span class="ep-count">{module.total_episodes} episodes</span>
    {/if}
    
    <div class="play-overlay">
      <span class="play-icon">▶</span>
    </div>
  </div>
  
  <div class="info">
    {#if module.category}
      <span class="badge badge-category">{module.category}</span>
    {/if}
    <p class="title">{module.title}</p>
  </div>
</a>

<style>
  .card {
    display: block;
    width: 240px;
    flex-shrink: 0;
    transition: transform 0.25s ease, box-shadow 0.25s ease;
    border-radius: 8px;
  }
  
  .card:hover {
    transform: translateY(-4px) scale(1.03);
    z-index: 10;
  }
  
  .thumb-wrap {
    position: relative;
    aspect-ratio: 16/9;
    border-radius: 8px;
    overflow: hidden;
    background: var(--surface2);
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }
  
  .thumb {
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.3s ease;
  }
  
  .card:hover .thumb {
    transform: scale(1.05);
  }
  
  .thumb-placeholder {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .thumb-icon {
    font-size: 2.5rem;
    opacity: 0.5;
    color: white;
  }
  
  .play-overlay {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0,0,0,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    opacity: 0;
    transition: opacity 0.2s ease;
  }
  
  .card:hover .play-overlay {
    opacity: 1;
  }
  
  .play-icon {
    font-size: 2.5rem;
    color: white;
    text-shadow: 0 2px 8px rgba(0,0,0,0.5);
    transition: transform 0.2s ease;
  }
  
  .card:hover .play-icon {
    transform: scale(1.1);
  }
  
  .progress-bar-container {
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: rgba(255,255,255,0.2);
    border-radius: 0 0 8px 8px;
    overflow: hidden;
  }
  
  .progress-bar {
    height: 100%;
    background: var(--accent);
    border-radius: 0 2px 0 0;
    transition: width 0.3s;
  }
  
  .ep-count {
    position: absolute;
    bottom: 8px;
    right: 8px;
    background: rgba(0,0,0,0.85);
    font-size: 0.7rem;
    padding: 0.2rem 0.5rem;
    border-radius: 4px;
    font-weight: 600;
    color: white;
    z-index: 2;
  }
  
  .info {
    padding: 0.6rem 0.2rem 0;
  }
  
  .title {
    font-size: 0.9rem;
    font-weight: 600;
    margin-top: 0.3rem;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    color: var(--text);
  }
  
  .badge {
    font-size: 0.65rem;
  }
  
  @media (max-width: 768px) {
    .card {
      width: 160px;
    }
  }
</style>

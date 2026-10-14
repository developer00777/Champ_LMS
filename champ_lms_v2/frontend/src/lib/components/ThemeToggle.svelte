<script lang="ts">
  import { theme } from '$lib/stores/theme';
  import Icon from './Icon.svelte';

</script>

<button
  class="toggle"
  class:dark={$theme === 'dark'}
  on:click={() => theme.toggle()}
  aria-label={$theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
  title={$theme === 'dark' ? 'Light mode' : 'Dark mode'}
>
  <span class="glyph sun"><Icon name="sun" size={19} /></span>
  <span class="glyph moon"><Icon name="moon" size={18} /></span>
</button>

<style>
  .toggle {
    position: relative;
    width: 42px;
    height: 42px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    color: var(--on-frame);
    background: rgba(255, 255, 255, 0.08);
    overflow: hidden;
  }
  .toggle:hover { background: rgba(255, 255, 255, 0.16); }
  .glyph {
    grid-area: 1 / 1;
    display: grid;
    transition: transform 520ms var(--ease-out), opacity 300ms var(--ease-out);
  }
  /* Light: sun up, moon parked below. Dark: they swap with a quarter turn. */
  .sun { transform: none; opacity: 1; color: #ffd66b; }
  .moon { transform: translateY(26px) rotate(-90deg); opacity: 0; color: #cfc6ff; }
  .dark .sun { transform: translateY(-26px) rotate(90deg); opacity: 0; }
  .dark .moon { transform: none; opacity: 1; }
  .toggle:hover .sun { transform: rotate(45deg); }
  .dark:hover .moon { transform: rotate(-18deg); }
</style>

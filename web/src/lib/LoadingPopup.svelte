<script>
  let { message = "Loading..." } = $props();
</script>

<div class="loading">
  <div class="spinner-ring">
    <div></div><div></div><div></div><div></div>
  </div>
  <p>{message}</p>
  <span class="hint">Please wait \u2014 avoid clicking repeatedly</span>
</div>

<style>
  .loading {
    text-align: center;
    padding: 3rem 2rem;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1rem;
  }
  .spinner-ring {
    display: inline-block;
    position: relative;
    width: 56px;
    height: 56px;
  }
  .spinner-ring div {
    box-sizing: border-box;
    display: block;
    position: absolute;
    width: 44px;
    height: 44px;
    margin: 6px;
    border: 4px solid transparent;
    border-radius: 50%;
    animation: ring-spin 1.2s cubic-bezier(0.5, 0, 0.5, 1) infinite;
    border-color: #7c7c9a transparent transparent transparent;
  }
  .spinner-ring div:nth-child(1) { animation-delay: -0.45s; }
  .spinner-ring div:nth-child(2) { animation-delay: -0.3s; }
  .spinner-ring div:nth-child(3) { animation-delay: -0.15s; }
  @keyframes ring-spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  p {
    font-family: monospace;
    font-size: 1rem;
    color: #e0e0e0;
    margin: 0;
  }
  .hint {
    font-family: monospace;
    font-size: 0.75rem;
    color: #5a5a7a;
    font-style: italic;
  }
</style>

<script>
  let input = $state("");

  function handleSubmit(e) {
    e.preventDefault();
    if (!input.trim()) return;
    // TODO: dispatch command to backend
    input = "";
  }
</script>

<form onsubmit={handleSubmit} class="command-bar">
  <input
    type="text"
    bind:value={input}
    placeholder="Type !command or ask naturally…"
    autofocus
  />
</form>

<style>
  .command-bar input {
    width: 100%;
    padding: 0.6rem 1rem;
    font-size: 1rem;
    border: 1px solid #ccc;
    border-radius: 6px;
    box-sizing: border-box;
  }
  .command-bar input:focus {
    outline: none;
    border-color: #4a90d9;
    box-shadow: 0 0 0 2px rgba(74, 144, 217, 0.2);
  }
</style>

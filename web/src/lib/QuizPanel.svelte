<script>
  /**
   * QuizPanel — interactive quiz component for review sessions.
   *
   * Props:
   *   data: object with session object containing uuid and mode
   *
   * Fetches questions via GET /api/v1/review/sessions/{uuid}/next
   * and records answers via POST /api/v1/review/answer.
   */
  let { data = {} } = $props();

  let sessionUuid = $derived(data?.session?.uuid || "");
  let sessionMode = $derived(data?.session?.mode || "quiz");

  let loading = $state(true);
  let question = $state(null);
  let done = $state(false);
  let feedback = $state(null); // { correct: bool, correctAnswer: string }
  let scoreCorrect = $state(0);
  let scoreTotal = $state(0);
  let selectedOption = $state(null);
  let error = $state(null);

  async function fetchNext() {
    if (!sessionUuid) return;
    loading = true;
    feedback = null;
    selectedOption = null;
    error = null;
    try {
      const resp = await fetch(`/api/v1/review/sessions/${sessionUuid}/next`);
      if (!resp.ok) {
        const detail = await resp.json().catch(() => ({}));
        error = detail.detail || `HTTP ${resp.status}`;
        return;
      }
      const data = await resp.json();
      if (data.done) {
        done = true;
        // Fetch final session stats
        const sessionResp = await fetch(`/api/v1/review/sessions/${sessionUuid}`);
        if (sessionResp.ok) {
          const sessionData = await sessionResp.json();
          scoreCorrect = sessionData.session?.correct || 0;
          scoreTotal = sessionData.session?.total || 0;
        }
        return;
      }
      question = data.question;
      scoreTotal = data.question?.position || 0;
    } catch (err) {
      error = `Network error: ${err.message}`;
    } finally {
      loading = false;
    }
  }

  async function handleAnswer(optionValue) {
    if (!question || feedback) return;
    selectedOption = optionValue;
    const isCorrect = optionValue === question.object_value;
    feedback = { correct: isCorrect, correctAnswer: question.object_label || question.object_value };
    if (isCorrect) scoreCorrect++;

    try {
      await fetch("/api/v1/review/answer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          result_uuid: question.uuid,
          is_correct: isCorrect,
          response: optionValue,
        }),
      });
    } catch (err) {
      // Non-critical — answer recorded locally regardless
      console.error("Failed to record answer:", err);
    }
  }

  async function handleNext() {
    await fetchNext();
  }

  // Load first question on mount
  $effect(() => {
    if (sessionUuid) {
      fetchNext();
    } else {
      error = "No session UUID provided.";
      loading = false;
    }
  });

  function renderValue(val) {
    if (val === null || val === undefined) return "";
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  }
</script>

<div class="quiz-panel">
  {#if error}
    <div class="error-banner">
      <p class="error-message">{error}</p>
      <p class="error-hint">Try <code>!review start mode=quiz</code> again.</p>
    </div>

  {:else if done}
    <div class="score-screen">
      <h2 class="score-title">Quiz Complete!</h2>
      <div class="score-circle">
        <span class="score-value">{scoreCorrect}</span>
        <span class="score-divider">/</span>
        <span class="score-total">{scoreTotal}</span>
      </div>
      <p class="score-pct">
        {scoreTotal > 0 ? Math.round(scoreCorrect / scoreTotal * 100) : 0}%
      </p>
      <p class="score-msg">
        {#if scoreTotal > 0 && scoreCorrect === scoreTotal}
          Perfect score! 🎉
        {:else if scoreTotal > 0 && scoreCorrect >= scoreTotal / 2}
          Good job!
        {:else}
          Keep practicing!
        {/if}
      </p>
    </div>

  {:else if loading}
    <div class="loading">
      <p>Loading question…</p>
    </div>

  {:else if question}
    <div class="question-card">
      <div class="q-header">
        <span class="q-num">Question {question.position} of {data?.session?.total || "?"}</span>
        <span class="q-mode-badge">Quiz</span>
      </div>

      <div class="q-prompt">
        <div class="q-row">
          <span class="q-label">Subject</span>
          <span class="q-value">{question.subject_label || question.subject_id}</span>
        </div>
        <div class="q-row">
          <span class="q-label">Predicate</span>
          <span class="q-value">{question.predicate_label || question.predicate_id}</span>
        </div>
      </div>

      <p class="q-task">Select the correct object:</p>

      <div class="options">
        {#each (question.options || [question.object_value]) as opt, i}
          <button
            class="option-btn"
            class:selected={selectedOption === opt}
            class:correct={feedback && opt === question.object_value}
            class:wrong={feedback && selectedOption === opt && opt !== question.object_value}
            disabled={!!feedback}
            onclick={() => handleAnswer(opt)}
          >
            <span class="opt-letter">{String.fromCharCode(65 + i)}</span>
            <span class="opt-text">{renderValue(opt)}</span>
            {#if feedback}
              {#if opt === question.object_value}
                <span class="opt-mark correct-mark">✓</span>
              {:else if selectedOption === opt}
                <span class="opt-mark wrong-mark">✗</span>
              {/if}
            {/if}
          </button>
        {/each}
      </div>

      {#if feedback}
        <div class="feedback" class:correct={feedback.correct} class:wrong={!feedback.correct}>
          <p>
            {#if feedback.correct}
              Correct!
            {:else}
              Wrong. The correct answer is: <strong>{feedback.correctAnswer}</strong>
            {/if}
          </p>
          <button class="btn-next" onclick={handleNext}>
            {question.position >= (data?.session?.total || 999) ? "See Results" : "Next Question"}
          </button>
        </div>
      {/if}
    </div>
  {:else}
    <div class="empty">
      <p>No questions available.</p>
    </div>
  {/if}
</div>

<style>
  .quiz-panel {
    display: flex;
    flex-direction: column;
    height: 100%;
    padding: 1rem;
    overflow-y: auto;
    font-family: monospace;
  }

  /* Error */
  .error-banner {
    text-align: center;
    padding: 2rem;
  }
  .error-message {
    color: #e74c3c;
    font-size: 0.9rem;
    margin-bottom: 0.5rem;
  }
  .error-hint {
    color: #7c7c9a;
    font-size: 0.8rem;
  }
  .error-hint code {
    background: #222;
    padding: 1px 4px;
    border-radius: 3px;
  }

  /* Loading */
  .loading {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #7c7c9a;
    font-size: 0.9rem;
  }

  /* Score screen */
  .score-screen {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100%;
    text-align: center;
  }
  .score-title {
    font-size: 1.3rem;
    color: #e0e0e0;
    margin-bottom: 1.5rem;
    font-weight: 400;
  }
  .score-circle {
    display: flex;
    align-items: baseline;
    gap: 0.2rem;
    margin-bottom: 0.5rem;
  }
  .score-value {
    font-size: 3rem;
    color: #6aaa6a;
    font-weight: 700;
  }
  .score-divider {
    font-size: 2rem;
    color: #555;
  }
  .score-total {
    font-size: 2rem;
    color: #aaa;
  }
  .score-pct {
    font-size: 1.1rem;
    color: #7c7c9a;
    margin-bottom: 0.75rem;
  }
  .score-msg {
    font-size: 0.95rem;
    color: #b0b0c0;
  }

  /* Question card */
  .question-card {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    max-width: 540px;
    margin: 0 auto;
    width: 100%;
  }
  .q-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.78rem;
    color: #7c7c9a;
  }
  .q-num {
    font-size: 0.8rem;
  }
  .q-mode-badge {
    background: #2a2a44;
    color: #8a8acc;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
  }

  .q-prompt {
    background: #1e1e32;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 0.75rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .q-row {
    display: flex;
    gap: 0.5rem;
    align-items: baseline;
  }
  .q-label {
    color: #7c7c9a;
    font-size: 0.78rem;
    min-width: 5rem;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .q-value {
    color: #e0e0e0;
    font-size: 0.95rem;
    word-break: break-word;
  }

  .q-task {
    font-size: 0.85rem;
    color: #b0b0c0;
    margin: 0;
  }

  .options {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .option-btn {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    background: #1a1a30;
    border: 1px solid #3a3a5a;
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    color: #d0d0e0;
    font-family: monospace;
    font-size: 0.88rem;
    cursor: pointer;
    transition: background 0.12s, border-color 0.12s;
    text-align: left;
    width: 100%;
  }
  .option-btn:hover:not(:disabled) {
    background: #2a2a44;
    border-color: #5a5a8a;
  }
  .option-btn:disabled {
    cursor: default;
    opacity: 0.9;
  }
  .option-btn.selected {
    border-color: #6a6a8a;
  }
  .option-btn.correct {
    background: #1a3a1a;
    border-color: #3a8a3a;
  }
  .option-btn.wrong {
    background: #3a1a1a;
    border-color: #8a3a3a;
  }
  .opt-letter {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 4px;
    background: #2a2a44;
    font-size: 0.78rem;
    font-weight: 600;
    color: #8a8acc;
    flex-shrink: 0;
  }
  .opt-text {
    flex: 1;
    word-break: break-word;
  }
  .opt-mark {
    font-size: 1rem;
    font-weight: 700;
    flex-shrink: 0;
  }
  .correct-mark { color: #4caf50; }
  .wrong-mark { color: #e74c3c; }

  .feedback {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    border-radius: 8px;
    font-size: 0.9rem;
    text-align: center;
  }
  .feedback.correct {
    background: #1a2a1a;
    border: 1px solid #3a6a3a;
    color: #6aaa6a;
  }
  .feedback.wrong {
    background: #2a1a1a;
    border: 1px solid #6a3a3a;
    color: #aa6a6a;
  }
  .feedback strong {
    color: #e0e0e0;
  }
  .btn-next {
    background: #2a2a44;
    color: #b0b0d0;
    border: 1px solid #4a4a6a;
    border-radius: 6px;
    padding: 0.4rem 1.2rem;
    font-family: monospace;
    font-size: 0.85rem;
    cursor: pointer;
    transition: background 0.1s;
  }
  .btn-next:hover {
    background: #3a3a5a;
  }

  /* Empty state */
  .empty {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: #7c7c9a;
    font-size: 0.9rem;
  }
</style>

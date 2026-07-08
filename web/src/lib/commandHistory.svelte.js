/** Reactive command history — re-exported from @lightercore/ui with app-specific key. */
import { createCommandHistory } from "@lightercore/ui/commandHistory.svelte.js";

export const history = createCommandHistory("semantika:commandHistory");

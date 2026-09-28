import type { Job, JobStep } from "./api";
import { isOpen } from "./jobs";

/**
 * One quiet line under an article's header, saying what the server is still doing to this word
 * (`docs/architecture/jobs.md`, "What the interface shows"). It shows work and never does it: the
 * only thing it can ask for is a new job, through Try again.
 *
 * It collapses when the job finishes. A failed step leaves one line until the owner dismisses it
 * or leaves the word.
 */

export interface StripLine {
  /** Each phase still ahead, in order; the one being worked on is `current`. */
  phases: { text: string; current: boolean }[];
  failure: string | null;
}

const PENDING = new Set(["pending", "running", "waiting"]);

/**
 * What a resting step is waiting for, appended to its phrase — or nothing, while it is not resting.
 *
 * The server names each provider that refused and why ("Gemini (free tier) is overloaded;
 * Cloudflare Workers AI is out of allowance for now"), and the job says when it will ask again. Both
 * are said, because "the provider is busy" was the whole of what a row of twelve stories showed for
 * an hour while two different things were wrong, one of which would not pass until midnight.
 */
function waitingNote(step: JobStep, job: Job | undefined, resting = step.state === "waiting"): string {
  if (!resting) return "";
  const due = job?.notBefore ? Date.parse(job.notBefore) : NaN;
  const next = Number.isFinite(due) && due > Date.now()
    ? new Date(due).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "";
  if (!step.waitingOn) return next ? ` (the provider is busy · next try ${next})` : " (the provider is busy)";
  return ` — ${step.waitingOn}${next ? ` · next try ${next}` : ""}`;
}

function phase(step: JobStep, job?: Job): string | null {
  const waiting = waitingNote(step, job);
  switch (step.name) {
    case "clips":
      return `Finding recorded examples${waiting}`;
    case "pictures":
      if (step.total) {
        return `Drawing ${Math.min((step.done ?? 0) + 1, step.total)} of ${step.total}${waiting}`;
      }
      return `Drawing pictures${waiting}`;
    case "pronunciations":
      return `Recording audio${waiting}`;
    case "draw":
      return `Drawing${waiting}`;
    case "corpus.update":
      return `Updating recorded speech${waiting}`;
    case "anki.push":
      return `Sending changes to Anki${waiting}`;
    case "anki.pull":
      return `Reading Anki's review state${waiting}`;
    case "brief":
      return `Writing picture briefs${waiting}`;
    /* A render is minutes of work in the companion container, and it reports both a fraction and a
       phrase as it goes — "Synthesizing speech", "Rendering the music bed", "Mixing" — so this says
       what is happening rather than only that something is. Its own words, not ours: it is the only
       thing that knows, and a sentence invented here would drift from it on the next release.

       `waiting` is deliberately not appended: this step waits because it is *following* a render,
       which is not the busy provider that suffix means. */
    case "loop.render": {
      const fraction = typeof step.detail?.progress === "number" ? step.detail.progress : null;
      const doing = typeof step.detail?.doing === "string" ? step.detail.doing : "";
      const words = typeof step.detail?.words === "number" ? step.detail.words : 0;
      const percent = fraction === null ? "" : ` · ${Math.round(fraction * 100)}%`;
      if (doing) return `${doing}${percent}`;
      return `Making the loop${words ? ` from ${words} words` : ""}${percent}`;
    }
    case "loop.store":
      return "Storing the track";
    case "capture": {
      const words = Array.isArray(step.detail?.words) ? step.detail.words.length : 0;
      return `Reading the text${words ? ` · ${words} so far` : ""}${waiting}`;
    }
    default:
      return null;
  }
}

function failureOf(step: JobStep): string {
  switch (step.name) {
    case "clips":
      return "Couldn't search recorded speech";
    case "pictures": {
      const refused = Number(step.detail?.refused ?? 0);
      if (step.total && refused) return `${step.total - refused} of ${step.total} pictures drawn`;
      return "The pictures could not be drawn";
    }
    case "pronunciations":
      return "Some audio could not be recorded";
    /* Lead with what happened and then say why. The `default` branch below already prefers
       `step.message`; returning a constant here threw away the one sentence that names the cause —
       which is how a render that died on a missing sample pack read as "could not be made". */
    case "loop.render":
      return step.message ? `The loop could not be made — ${step.message}` : "The loop could not be made";
    case "loop.store":
      return step.message
        ? `The loop was made but its track could not be stored — ${step.message}`
        : "The loop was made but its track could not be stored";
    /* Lead with what happened and then say why, exactly as the loop steps do: a constant here is
       what turns a refusal that named the reason into one that names nothing. */
    case "story.write":
      return step.message ? `The story could not be written — ${step.message}` : "The story could not be written";
    case "story.translate":
      return step.message ? `The story could not be translated — ${step.message}` : "The story could not be translated";
    case "story.brief":
      return step.message ? `The pictures could not be planned — ${step.message}` : "The pictures could not be planned";
    case "story.draw":
      return step.message ? `Some pictures could not be drawn — ${step.message}` : "Some pictures could not be drawn";
    case "story.audio":
      return step.message ? `Some parts could not be recorded — ${step.message}` : "Some parts could not be recorded";
    case "corpus.update":
      return "The recorded-speech corpus could not be updated";
    default:
      return step.message || "Something could not be finished";
  }
}

/**
 * What each of a story's steps takes of the whole, **by how long it actually takes** — measured from
 * real jobs on a real deployment rather than guessed: writing, translating and briefing together are
 * about fifteen seconds, four pictures about a minute, and four parts of narration about two. The
 * three text steps therefore share a tenth of the bar between them. Splitting it evenly, as it was,
 * put half the bar on the fastest fifth of the work, so the figure shot to 45% in a few seconds and
 * then crawled — which is the one thing a progress figure must not do.
 *
 * Only `story.draw` and `story.audio` can say how far through themselves they are, and only they are
 * long enough for it to matter.
 */
const STORY_WEIGHTS: Record<string, number> = {
  "story.write": 5, "story.translate": 3, "story.brief": 2, "story.draw": 35, "story.audio": 55
};

/** The steps that report `done` of `total`, and so count for part of their weight while running. */
const STORY_COUNTED = new Set(["story.draw", "story.audio"]);

const STORY_FINISHED = new Set(["done", "skipped", "failed"]);

function storyLabel(step: JobStep, job: Job, resting = step.state === "waiting"): string {
  const waiting = waitingNote(step, job, resting);
  switch (step.name) {
    /* One message for the three text steps. They take a few seconds between them, so naming each
       one flashes three phrases past faster than they can be read, and "writing the story" is what
       all three of them are. A *failure* still names the step it happened in — `failureOf` does
       that, and there the distinction is the whole point. */
    case "story.write":
    case "story.translate":
    case "story.brief":
      return `Writing the story${waiting}`;
    case "story.audio":
      if (step.total) {
        return `Recording part ${Math.min((step.done ?? 0) + 1, step.total)} of ${step.total}${waiting}`;
      }
      return `Recording the story${waiting}`;
    default:
      if (step.total) {
        return `Drawing picture ${Math.min((step.done ?? 0) + 1, step.total)} of ${step.total}${waiting}`;
      }
      return `Drawing the pictures${waiting}`;
  }
}

/**
 * A story is made in five steps, but to the person waiting it is one piece of work: so this says how
 * far through the whole it is, first, and only then which part of it is going on. The loop line puts
 * its phrase first because the render's own words are the news there; here the number is, and it is
 * a fraction of everything rather than of the step.
 *
 * **"Waiting to start" means waiting to start, and nothing else.** It used to be what came out
 * whenever no step was *running* — which is true before the job is picked up, and false in two
 * common cases that between them covered most of a slow story: a step that is resting out a busy
 * provider is put back to `pending`, so a ten-minute rest read as "waiting to start", and once every
 * step has finished the job is still open for as long as it takes to close, so the line said
 * "waiting to start" at 99%.
 */
function storyLine(job: Job): StripLine {
  const steps = job.steps.filter((step) => step.name in STORY_WEIGHTS);
  const whole = steps.reduce((sum, step) => sum + STORY_WEIGHTS[step.name], 0);
  const finished = steps.reduce((sum, step) => {
    const weight = STORY_WEIGHTS[step.name];
    if (step.state === "done" || step.state === "skipped") return sum + weight;
    // Only these report a count, so only they count for part of their weight.
    if (STORY_COUNTED.has(step.name) && step.total) return sum + weight * Math.min((step.done ?? 0) / step.total, 1);
    return sum;
  }, 0);
  // Rounded down and held under 100, because this only runs while the job is open: a line that says
  // 100% and is still going is a small lie, and the last picture's step is when it would tell it.
  const percent = whole ? Math.min(Math.floor((finished / whole) * 100), 99) : 0;

  const current = steps.find((step) => step.state === "running" || step.state === "waiting")
    ?? steps.find((step) => !STORY_FINISHED.has(step.state));
  const started = steps.some((step) => step.state !== "pending");
  // Resting between steps: the step was put back to `pending` and the job told to wait, so the row
  // itself is what says a provider is being waited for rather than the step.
  const resting = Boolean(job.notBefore) && Date.parse(job.notBefore!) > Date.now();
  const text = !started ? "Waiting to start"
    : !current ? "Finishing"
      : storyLabel(current, job, current.state === "waiting" || (resting && current.state === "pending"));
  return { phases: [{ text: `${percent}% · ${text}`, current: true }], failure: null };
}

/** What the strip says for a job, or null when it should not be there at all. */
export function stripOf(job: Job | undefined): StripLine | null {
  if (!job || job.state === "cancelled" || job.state === "done") return null;
  if (isOpen(job) && job.kind === "story") return storyLine(job);
  if (isOpen(job)) {
    const phases = job.steps
      .filter((step) => PENDING.has(step.state))
      .map((step) => ({ text: phase(step, job), current: step.state !== "pending" }))
      .filter((entry): entry is { text: string; current: boolean } => entry.text !== null);
    if (!phases.length) return { phases: [{ text: "Waiting to start", current: false }], failure: null };
    return { phases, failure: null };
  }
  const failed = job.steps.find((step) => step.state === "failed");
  if (failed) return { phases: [], failure: failureOf(failed) };
  return { phases: [], failure: job.error === "interrupted"
    ? "Interrupted when the server restarted"
    : job.message || "Something could not be finished" };
}

export default function ProgressStrip({ job, onRetry, onDismiss }: {
  job: Job | undefined;
  onRetry(): void;
  onDismiss(): void;
}) {
  const line = stripOf(job);
  if (!line) return null;
  if (line.failure) {
    return <div className="progress-strip failed" role="status">
      <span>{line.failure}</span>
      <span className="sep">·</span>
      <button type="button" className="strip-action" onClick={onRetry}>Try again</button>
      <button type="button" className="strip-dismiss" aria-label="Dismiss" onClick={onDismiss}>×</button>
    </div>;
  }
  return <div className="progress-strip" role="status" aria-live="polite">
    {line.phases.map((entry, index) => <span key={entry.text}>
      {index > 0 && <span className="sep">·</span>}
      <span className={entry.current ? "now" : undefined}>{entry.text}</span>
    </span>)}
  </div>;
}

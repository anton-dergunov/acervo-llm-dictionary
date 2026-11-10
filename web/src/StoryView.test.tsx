import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Job } from "./api";
import { jobStream } from "./jobs";
import StoryView from "./StoryView";
import { testGraph } from "./testGraph";

vi.mock("./picture", () => ({
  usePicture: () => ({ url: "blob:picture", error: null })
}));

function view(overrides: Partial<Parameters<typeof StoryView>[0]> = {}) {
  const props = {
    graph: testGraph(), language: "es", languageName: "Spanish",
    onClose: vi.fn(), onDelete: vi.fn(),
    ...overrides
  };
  return { ...render(<StoryView {...props} />), props };
}

describe("the stories surface", () => {
  it("lists a written story by its own title", () => {
    view();
    expect(screen.getByRole("button", { name: /La balsa que picaba/ })).toBeInTheDocument();
  });

  /* A story's state is derived: no parts is the whole of what "never written" means, and there is
     no status column that could disagree with it. */
  it("says a story that was asked for and never written has not been", () => {
    view();
    expect(screen.getByText(/Never written/)).toBeInTheDocument();
  });

  it("names a story that has no title by the words it was asked to teach", () => {
    view();
    // The queued story has no title, so its words stand in for one.
    expect(screen.getByRole("button", { name: /^picar/ })).toBeInTheDocument();
  });

  it("lists the words a written story was made from, in the order they were asked for", () => {
    view();
    expect(screen.getByText("la balsa · picar")).toBeInTheDocument();
  });

  it("counts a story's parts and words, and says how many pictures have been drawn", () => {
    view();
    expect(screen.getByText("2 parts · 2 words")).toBeInTheDocument();
    expect(screen.getByText("1 of 2 drawn")).toBeInTheDocument();
  });

  it("opens a written story and comes back out of it", () => {
    view();
    fireEvent.click(screen.getByRole("button", { name: /La balsa que picaba/ }));
    // Two parts, and the page of words after them.
    expect(screen.getByText("1 / 3")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Back to the stories" }));
    expect(screen.getByRole("heading", { name: "Stories" })).toBeInTheDocument();
  });

  it("does not open a story that was never written", () => {
    view();
    fireEvent.click(screen.getByRole("button", { name: /^picar/ }));
    expect(screen.getByRole("heading", { name: "Stories" })).toBeInTheDocument();
  });

  /* A surface that replaces the list has to carry the way back out of itself, at every width. */
  it("goes back to the words with the back arrow", () => {
    const { props } = view();
    fireEvent.click(screen.getByRole("button", { name: "Back to the list" }));
    expect(props.onClose).toHaveBeenCalled();
  });

  /* The head is the word list's: a count, and the orders. Make is the top bar's Add here. */
  it("counts its stories and offers the orders, with no Make button of its own", () => {
    view();
    expect(screen.getByText("2 in Spanish")).toBeInTheDocument();
    for (const order of ["Recent", "Hardest", "Rarest"]) expect(screen.getByRole("button", { name: order })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Make a story/ })).not.toBeInTheDocument();
  });

  /* The top bar's search, on this surface, searches the words in its stories — and each story it
     keeps says which of its words matched, so none turns up for no visible reason. */
  it("keeps the stories whose words match the search, and says which word matched", () => {
    view({ query: "balsa" });
    expect(screen.getByText("1 story with “balsa”")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /La balsa que picaba/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^picar/ })).not.toBeInTheDocument();
    expect(document.querySelector(".made-match mark")?.textContent).toBe("balsa");
  });

  it("says so when no story uses the word searched for", () => {
    view({ query: "zzz" });
    expect(screen.getByText("No story of yours uses “zzz”.")).toBeInTheDocument();
  });

  it("deletes from the right-click menu", () => {
    const { props } = view();
    fireEvent.contextMenu(screen.getByRole("button", { name: /La balsa que picaba/ }).closest(".swipe-item")!);
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete this story" }));
    expect(props.onDelete).toHaveBeenCalledWith("storypicada0001");
  });

  it("says so when there are no stories at all", () => {
    view({ language: "de" });
    expect(screen.getByText(/No stories yet/)).toBeInTheDocument();
  });
});


describe("a story that is still being made", () => {
  const making = (steps: Job["steps"]): Job => ({
    id: "job000000000001", ownerId: "owner0000000001", parentId: null, kind: "story",
    subject: { kind: "story", id: "storypicada0001" }, input: {}, state: "running",
    trigger: "manual", steps, rerun: false, cancelRequested: false, dismissed: false,
    error: null, message: null, notBefore: null, createdAt: "2026-09-20T10:00:00.000Z",
    startedAt: "2026-09-20T10:00:00.000Z", finishedAt: null
  });

  function withJob(steps: Job["steps"]) {
    const job = making(steps);
    vi.spyOn(jobStream, "getStatus").mockReturnValue({
      jobs: [job], bySubject: new Map([["story:storypicada0001", job]]), connected: true
    } as ReturnType<typeof jobStream.getStatus>);
    vi.spyOn(jobStream, "subscribe").mockImplementation(() => () => undefined);
    return view();
  }

  afterEach(() => vi.restoreAllMocks());

  /* The figure used to vanish the moment the first part landed, and the recording then ran for
     half an hour with nothing on screen to say so. */
  it("shows the one figure even once it has parts, and says it can be read", () => {
    withJob([
      { name: "story.write", state: "done" }, { name: "story.translate", state: "done" },
      { name: "story.brief", state: "done" }, { name: "story.draw", state: "done" },
      { name: "story.audio", state: "running", done: 1, total: 4 }
    ]);

    expect(screen.getByText(/Recording part 2 of 4/)).toBeInTheDocument();
    expect(screen.getByText("Ready to read")).toBeInTheDocument();
    expect(screen.queryByText("2 parts · 2 words")).not.toBeInTheDocument();
  });

  it("says when it is the provider holding things up, rather than going quiet", () => {
    withJob([
      { name: "story.write", state: "done" }, { name: "story.translate", state: "done" },
      { name: "story.brief", state: "done" }, { name: "story.draw", state: "done" },
      { name: "story.audio", state: "waiting", done: 1, total: 4, rests: 6 }
    ]);

    expect(screen.getByText(/the provider is busy/)).toBeInTheDocument();
  });
});

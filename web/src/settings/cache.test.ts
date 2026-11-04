/** What Settings remembers of the server's answers, and when it must forget them. */

import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { forgetServerSettings, refresh, store, useServerSetting, type Resource } from "./cache";

const resource = (fetch: () => Promise<number>, key = "test"): Resource<number> =>
  ({ key, fetch, failure: "It could not be read." });

describe("a setting the server holds", () => {
  it("shows the last answer at once on the next visit, and asks again behind it", async () => {
    let answer = 1;
    const fetch = vi.fn(async () => answer);
    const source = resource(fetch);

    const first = renderHook(() => useServerSetting(source));
    await waitFor(() => expect(first.result.current.value).toBe(1));
    first.unmount();

    answer = 2;
    let release!: () => void;
    fetch.mockImplementationOnce(() => new Promise((resolve) => { release = () => resolve(answer); }));
    const second = renderHook(() => useServerSetting(source));
    // The page that comes back is never empty while it waits: that was the blink.
    expect(second.result.current.value).toBe(1);
    act(() => release());
    await waitFor(() => expect(second.result.current.value).toBe(2));
  });

  it("asks once when two pages ask at the same time", async () => {
    const fetch = vi.fn(async () => 7);
    const source = resource(fetch, "shared");
    await Promise.all([refresh(source), refresh(source)]);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("does not let an answer that began before a save undo it", async () => {
    let release!: (value: number) => void;
    const source = resource(() => new Promise((resolve) => { release = resolve; }), "raced");
    const shown = renderHook(() => useServerSetting(source));
    act(() => store(source, 5));
    await act(async () => { release(1); });
    expect(shown.result.current.value).toBe(5);
  });

  it("says why only when there is nothing to show, and keeps a value a refresh could not renew", async () => {
    const fetch = vi.fn<() => Promise<number>>().mockRejectedValueOnce(new Error("offline"));
    const source = resource(fetch, "flaky");
    const first = renderHook(() => useServerSetting(source));
    await waitFor(() => expect(first.result.current.error).toBe("It could not be read."));
    first.unmount();

    fetch.mockResolvedValueOnce(3);
    const second = renderHook(() => useServerSetting(source));
    await waitFor(() => expect(second.result.current.value).toBe(3));
    second.unmount();

    fetch.mockRejectedValueOnce(new Error("offline"));
    const third = renderHook(() => useServerSetting(source));
    await act(async () => { await refresh(source).catch(() => undefined); });
    expect(third.result.current).toMatchObject({ value: 3, error: null });
  });

  it("forgets everything on signing out, including an answer still on its way", async () => {
    let release!: (value: number) => void;
    const source = resource(() => new Promise((resolve) => { release = resolve; }), "account");
    store(source, 9);
    const shown = renderHook(() => useServerSetting(source));
    act(() => forgetServerSettings());
    expect(shown.result.current.value).toBeUndefined();
    await act(async () => { release(4); });
    expect(shown.result.current.value).toBeUndefined();
  });
});

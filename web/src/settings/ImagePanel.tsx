/**
 * Settings ▸ Pictures: whether they are drawn unattended, and which styles are in play.
 *
 * Two settings and deliberately not a third. Rounds 1–7 of the prompt work tried per-style weights
 * and a sampled menu; what survived is that the owner should say *which styles exist for them* and
 * *how adventurously to choose among them*. A weight is a number nobody can set meaningfully
 * without running a few hundred pictures and counting, which is what the histogram in
 * `experiments/sense-images/` is for and not what a settings screen is for.
 *
 * Owner-scoped **server** state, unlike the editor's wrapping preference: the drawing happens on
 * the server, so a phone that has never opened this screen must still get the styles chosen here.
 */

import { useRef } from "react";
import { AcervoApiError, backendSession, type ImageSettings } from "../api";
import { CheckIcon } from "../icons";
import { SETTINGS, useServerSetting } from "./cache";
import { Group, Notice, Placeholder, Toggle } from "./kit";

type Changes = Partial<Pick<ImageSettings, "drawEnabled" | "stylesOff" | "boostVariety">>;

export default function ImagePanel({ onNotify }: { onNotify(message: string): void }) {
  const { value: settings, error, set } = useServerSetting(SETTINGS.images);
  /**
   * What this screen believes, updated in the same breath as the state.
   *
   * `settings` is what React renders and lags a tick behind; this is what the *next* click has to
   * compute from. Switching off four styles in a row is one gesture, and each click has to add to
   * the previous one rather than to whatever the last render happened to hold.
   */
  const intended = useRef<ImageSettings | null>(null);
  /** Saves in flight. With none, what is shown is what the server said, refreshed or not. */
  const pending = useRef(0);
  if (pending.current === 0) intended.current = settings ?? null;
  /** Only the newest answer counts: two saves can return out of order. */
  const newest = useRef(0);

  const commit = (next: ImageSettings) => {
    intended.current = next;
    set(next);
  };

  /**
   * Move the switch at once, then reconcile with what the server stored.
   *
   * The switch *is* the feedback, which is why there is no "Saving…" line. Optimism with a way back:
   * a refused change restores exactly what was showing before it, so a switch never sits in a state
   * the server does not hold.
   */
  const apply = async (changes: Changes) => {
    const before = intended.current;
    if (!before) return;
    const token = ++newest.current;
    pending.current += 1;
    commit({ ...before, ...changes, chosen: true });
    try {
      const stored = await backendSession.saveImageSettings(changes);
      if (newest.current === token) commit(stored);
    } catch (error) {
      if (newest.current === token) commit(before);
      onNotify(error instanceof AcervoApiError ? error.message : "That change was not saved.");
    } finally {
      pending.current -= 1;
    }
  };

  if (!settings) return error ? <Notice>{error}</Notice> : <Placeholder rows={2} />;

  const off = new Set(settings.stylesOff);
  const toggle = (styleId: string, on: boolean) => {
    const next = new Set(intended.current?.stylesOff ?? []);
    if (on) next.delete(styleId); else next.add(styleId);
    void apply({ stylesOff: [...next] });
  };

  return <>
    {!settings.available && <Notice>
      No picture provider is set up on this server, so nothing will be drawn. See Providers.
    </Notice>}

    <Group>
      <Toggle
        label="Draw pictures" hint="New words get their pictures on their own"
        checked={settings.drawEnabled} onChange={(on) => void apply({ drawEnabled: on })}
      />
      <Toggle
        label="Push for stylistic variety" hint="Less predictable, more varied styles"
        checked={settings.boostVariety} onChange={(on) => void apply({ boostVariety: on })}
      />
    </Group>

    <Group
      title="Styles" count={`${settings.styles.length - off.size} of ${settings.styles.length} on`}
      foot={settings.chosen
        ? "The writer picks the style that suits each meaning. One always stays on."
        : "Nothing chosen yet, so this server’s defaults are in force."}
    >
      <div className="pref-chips">
        {settings.styles.map((style) => {
          const on = !off.has(style.id);
          return <button
            key={style.id} type="button" className="pref-chip" aria-pressed={on}
            onClick={() => toggle(style.id, !on)}
          >{on && <CheckIcon />}{style.label}{style.mono && <span className="label"> mono</span>}</button>;
        })}
      </div>
      {/* Twenty-three switches, so the two bulk moves earn their place: the working gesture for
          "just these three" is clear-then-tick. Switching all on sends an empty off-list, which is
          also what a fresh account holds, so it doubles as the way back to the deployment's default. */}
      <div className="pref-row pref-buttons">
        <button type="button" className="tb-btn" onClick={() => void apply({ stylesOff: [] })} disabled={off.size === 0}>
          Switch all on
        </button>
        {/* All but the first, which is `cinematic-photoreal`: the one register the template says can
            carry any meaning at all, so it is the least bad thing to be left with. */}
        <button
          type="button" className="tb-btn"
          onClick={() => void apply({ stylesOff: settings.styles.slice(1).map((style) => style.id) })}
          disabled={off.size >= settings.styles.length - 1}
        >Switch all off</button>
      </div>
    </Group>
  </>;
}

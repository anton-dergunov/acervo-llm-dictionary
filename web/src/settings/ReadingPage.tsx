/**
 * Settings ▸ Reading: how a word opens, how the IPA guide is laid out while it is being tried, and
 * how its YAML is shown. All describe this device, not the vocabulary, so they are kept on the device
 * and never synced.
 */

import { useState } from "react";
import {
  articleViewPreference, editorPreferences, setArticleViewPreference, setEditorPreference,
  type ArticleViewPreference, type EditorPreferences
} from "../editorPreferences";
import { setIpaTrial, useIpaTrial, type MarksLayout, type PhoneLayout } from "../ipa/trial";
import { Group, Segmented, Toggle } from "./kit";

export default function ReadingPage() {
  const [editor, setEditor] = useState(editorPreferences);
  const [view, setView] = useState(articleViewPreference);
  const trial = useIpaTrial();

  const change = (name: keyof EditorPreferences) => (value: boolean) => {
    setEditorPreference(name, value);
    setEditor(editorPreferences());
  };

  return <>
    <Group title="Articles">
      <Segmented<ArticleViewPreference>
        label="Open words as" value={view}
        options={[
          { value: "auto", label: "Automatic", hint: "Cards on a touch screen, Page with a mouse" },
          { value: "page", label: "Page", hint: "The whole entry, where you can ask and edit" },
          { value: "cards", label: "Cards", hint: "One meaning and one sentence at a time" }
        ]}
        onChange={(value) => { setArticleViewPreference(value); setView(value); }}
      />
    </Group>
    <Group title="IPA guide (trial)" foot="Tap a transcription to try them. Kept until one of each is chosen.">
      <Segmented<PhoneLayout>
        label="On a phone" value={trial.phone}
        options={[
          { value: "sheet", label: "Sheet", hint: "Slides up over the lower part of the screen" },
          { value: "full", label: "Full screen", hint: "Covers the screen until you close it" },
          { value: "inline", label: "Inline", hint: "Opens in the article, under the transcription" }
        ]}
        onChange={(value) => setIpaTrial("phone", value)}
      />
      <Segmented<MarksLayout>
        label="Marks" value={trial.marks}
        options={[
          { value: "inside", label: "In the letter's row", hint: "ʰ, ̯ or ː explained under their letter; stress at the top" },
          { value: "rows", label: "Rows of their own", hint: "Every mark, stress too, on a row after its letter" }
        ]}
        onChange={(value) => setIpaTrial("marks", value)}
      />
    </Group>
    <Group title="YAML editor" foot="These apply to this device only.">
      <Toggle label="Wrap long lines" checked={editor.wrap} onChange={change("wrap")} />
      <Toggle
        label="Show line numbers" hint="A refused document names the line it is on"
        checked={editor.numbers} onChange={change("numbers")}
      />
    </Group>
  </>;
}

/**
 * Settings ▸ Reading: how a word opens and how its YAML is shown. Both describe this device, not the
 * vocabulary, so they are kept on the device and never synced.
 */

import { useState } from "react";
import {
  articleViewPreference, editorPreferences, setArticleViewPreference, setEditorPreference,
  type ArticleViewPreference, type EditorPreferences
} from "../editorPreferences";
import { Group, Segmented, Toggle } from "./kit";

export default function ReadingPage() {
  const [editor, setEditor] = useState(editorPreferences);
  const [view, setView] = useState(articleViewPreference);

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
    <Group title="YAML editor" foot="These apply to this device only.">
      <Toggle label="Wrap long lines" checked={editor.wrap} onChange={change("wrap")} />
      <Toggle
        label="Show line numbers" hint="A refused document names the line it is on"
        checked={editor.numbers} onChange={change("numbers")}
      />
    </Group>
  </>;
}

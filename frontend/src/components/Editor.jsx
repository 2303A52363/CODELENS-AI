import { useMemo } from "react";
import CodeMirror from "@uiw/react-codemirror";
import { python } from "@codemirror/lang-python";
import { javascript } from "@codemirror/lang-javascript";
import { cpp } from "@codemirror/lang-cpp";
import { java } from "@codemirror/lang-java";
import { html } from "@codemirror/lang-html";
import { css } from "@codemirror/lang-css";
import { sql } from "@codemirror/lang-sql";
import { EditorView, Decoration } from "@codemirror/view";
const LANG = { python, javascript, c: cpp, cpp, java, html, css, sql };
export default function Editor({ value, onChange, errorLine, language = "python", readOnly = false, height = "380px", theme = "light" }) {
  const ext = useMemo(() => {
    const e = [(LANG[language] || python)(), EditorView.lineWrapping];
    if (errorLine) e.push(EditorView.decorations.of((view) => {
      if (errorLine > view.state.doc.lines) return Decoration.none;
      return Decoration.set([Decoration.line({ class: "cm-error-line" }).range(view.state.doc.line(errorLine).from)]);
    }));
    return e;
  }, [errorLine, language]);
  return <CodeMirror value={value} height={height} theme={theme} extensions={ext} onChange={onChange} readOnly={readOnly}
    basicSetup={{ lineNumbers: true, highlightActiveLine: !readOnly, foldGutter: false }} />;
}

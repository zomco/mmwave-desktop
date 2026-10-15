import { describe, expect, it } from "vitest";
import { readTheme } from "./theme";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { Button, Icon, Spinner } from "./ui";

describe("MMWave family controls", () => {
  it("ignores missing or invalid stored preferences", () => {
    for (const value of [null, "", "invalid", "system"]) expect(readTheme(value)).toBe("system");
    expect(readTheme("light")).toBe("light");
    expect(readTheme("dark")).toBe("dark");
  });
  it("preserves form semantics, disabled state and accessible names", () => {
    const html = renderToStaticMarkup(createElement(Button, { variant: "primary", type: "submit", disabled: true, "aria-label": "保存" }, "保存"));
    expect(html).toContain("ui-button-primary");
    expect(html).toContain('type="submit"');
    expect(html).toContain('disabled=""');
    expect(html).toContain('aria-label="保存"');
  });
  it("keeps decoration out of the accessible name and exposes loading status", () => {
    expect(renderToStaticMarkup(createElement(Icon, { name: "radar" }))).toContain('aria-hidden="true"');
    expect(renderToStaticMarkup(createElement(Spinner))).toContain('role="status"');
  });
});

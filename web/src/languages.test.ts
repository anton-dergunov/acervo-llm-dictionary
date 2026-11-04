import { describe, expect, it } from "vitest";
import { automaticFlag, flagFor, flagOf, languageName, mainRegion, varietyOptions } from "./languages";

describe("languages", () => {
  it("draws a region's flag, and a globe for a region wider than a country", () => {
    expect(flagOf("AR")).toBe("🇦🇷");
    expect(flagOf("gb")).toBe("🇬🇧");
    expect(flagOf("419")).toBe("🌐");
    expect(flagOf(null)).toBe("🌐");
  });

  it("knows where a language is most likely spoken, offline", () => {
    expect(mainRegion("es")).toBe("ES");
    expect(mainRegion("zh-Hant")).toBe("TW");
    expect(languageName("zh-Hans")).toBe("Chinese (Simplified)");
  });

  it("shows the owner's own flag, else the variety's, else the language's", () => {
    expect(flagFor({ language: "es", flag: "🏴", region: "AR" })).toBe("🏴");
    expect(flagFor({ language: "es", flag: null, region: "AR" })).toBe("🇦🇷");
    expect(flagFor({ language: "es", flag: null, region: null })).toBe("🇪🇸");
    expect(automaticFlag("fr", null)).toBe("🇫🇷");
  });

  it("offers the server's varieties first, then a voice's, then the one already chosen", () => {
    expect(varietyOptions(["MX", "AR"], ["es-US"], "CL").map((option) => option.label))
      .toEqual(["🇲🇽 Mexico", "🇦🇷 Argentina", "🇺🇸 United States", "🇨🇱 Chile"]);
  });
});

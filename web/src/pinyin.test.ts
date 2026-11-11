import { describe, expect, it } from "vitest";
import { isMandarin } from "./languages";
import {
  accentedPinyin, accentedPinyinInText, alignHanzi, isNumberedPinyin, pinyinSearchForms, pinyinSyllables
} from "./pinyin";
import vectors from "./testFixtures/pinyinVectors.json";

describe("accentedPinyin", () => {
  it("agrees with the server's copy on every shared case", () => {
    // `tests/unit/test_pinyin.py` reads the same file: Anki's cards are marked by the Python twin.
    for (const [numbered, marked] of vectors.cases) expect(accentedPinyin(numbered)).toBe(marked);
  });

  it("marks the tone where the rule puts it", () => {
    expect(accentedPinyin("han4 zi4")).toBe("hàn zì");
    expect(accentedPinyin("Fang1 shan1 Xian4")).toBe("Fāng shān Xiàn");
    expect(accentedPinyin("ni2 jiang1")).toBe("ní jiāng");
    // `a` and `e` win wherever they are; `ou` marks the o; otherwise the last vowel takes it.
    expect(accentedPinyin("hao3")).toBe("hǎo");
    expect(accentedPinyin("gou3")).toBe("gǒu");
    expect(accentedPinyin("hui4")).toBe("huì");
    expect(accentedPinyin("xie4")).toBe("xiè");
  });

  it("writes ü for both spellings an ASCII format uses", () => {
    expect(accentedPinyin("Lu:3 liang2")).toBe("Lǚ liáng");
    expect(accentedPinyin("nv3")).toBe("nǚ");
  });

  it("drops the digit for a neutral tone rather than marking it", () => {
    expect(accentedPinyin("ma5")).toBe("ma");
    expect(accentedPinyin("de0")).toBe("de");
  });

  it("leaves alone anything that is not numbered pinyin", () => {
    expect(accentedPinyin("hàn zì")).toBe("hàn zì");
    expect(accentedPinyin("てあらいき")).toBe("てあらいき");
    expect(accentedPinyin("/maloˈɡɾaɾ/")).toBe("/maloˈɡɾaɾ/");
    expect(isNumberedPinyin("case study")).toBe(false);
  });

  it("marks the cross-references CC-CEDICT writes inside a definition", () => {
    expect(accentedPinyinInText("a county in Lüliang City 呂梁市|吕梁市[Lu:3 liang2 Shi4], Shanxi"))
      .toBe("a county in Lüliang City 呂梁市|吕梁市[Lǚ liáng Shì], Shanxi");
    // Some builds space out the `u:` that stands for `ü`; closing it up is what makes them read.
    expect(accentedPinyinInText("City 呂梁市|吕梁市[Lu : 3 liang2 Shi4], Shanxi"))
      .toBe("City 呂梁市|吕梁市[Lǚ liáng Shì], Shanxi");
    // An IPA transcription in brackets is not a reading and must survive untouched.
    expect(accentedPinyinInText("noise [bʲɪɡlʲɪˈt͡sax]")).toBe("noise [bʲɪɡlʲɪˈt͡sax]");
  });
});

const shown = (reading: string) => pinyinSyllables(reading)?.map((one) => `${one.before}${one.text}${one.tone}`).join("|");

describe("pinyinSyllables", () => {
  it("reads numbered and marked Pinyin as the same syllables", () => {
    expect(shown("tu2 shu1 guan3")).toBe("tú2| shū1| guǎn3");
    expect(shown("tú shū guǎn")).toBe("tú2| shū1| guǎn3");
    expect(shown("Běijīng")).toBe("Běi3|jīng1");
  });

  it("cuts a run of syllables at the one mark each may carry", () => {
    expect(shown("túshūguǎn")).toBe("tú2|shū1|guǎn3");
    expect(shown("zhuāngxiū")).toBe("zhuāng1|xiū1");
    expect(shown("xīān")).toBe("xī1|ān1");
    expect(shown("Xī'ān")).toBe("Xī1|'ān1");
    expect(shown("tu2shu1guan3")).toBe("tú2|shū1|guǎn3");
  });

  it("treats an unmarked syllable among marked ones as neutral", () => {
    expect(shown("māma")).toBe("mā1|ma5");
    expect(shown("ma1 ma5")).toBe("mā1| ma5");
  });

  it("keeps the r of erhua on its syllable", () => {
    const written = pinyinSyllables("yìdiǎnr")!;
    expect(written.map((one) => [one.text, one.erhua])).toEqual([["yì", false], ["diǎnr", true]]);
    // CC-CEDICT spells the same 儿 as a syllable of its own.
    expect(pinyinSyllables("yi1 dian3 r5")!.map((one) => one.text)).toEqual(["yī", "diǎnr"]);
    // `ér` is a syllable, not erhua.
    expect(pinyinSyllables("nǚ'ér")!.map((one) => [one.text, one.erhua])).toEqual([["nǚ", false], ["ér", false]]);
  });

  it("spells ü the way Pinyin does after each initial", () => {
    expect(pinyinSyllables("nv3 lu:4")!.map((one) => one.text)).toEqual(["nǚ", "lǜ"]);
    expect(pinyinSyllables("xv3")!.map((one) => one.text)).toEqual(["xǔ"]);
  });

  it("refuses what is not Pinyin, and Pinyin with no tones to show", () => {
    expect(pinyinSyllables("tu shu guan")).toBeNull();
    expect(pinyinSyllables("/maloˈɡɾaɾ/")).toBeNull();
    expect(pinyinSyllables("case study")).toBeNull();
    expect(pinyinSyllables("gwong2 zau1")).toBeNull();
    expect(pinyinSyllables("")).toBeNull();
  });
});

describe("alignHanzi", () => {
  const columns = (headword: string, reading: string) =>
    alignHanzi(headword, pinyinSyllables(reading)!)?.map((column) => `${column.characters}:${column.syllable.text}`);

  it("pairs each character with the syllable that reads it", () => {
    expect(columns("图书馆", "tu2 shu1 guan3")).toEqual(["图:tú", "书:shū", "馆:guǎn"]);
  });

  it("gives 儿 to the syllable whose r it is", () => {
    expect(columns("一点儿", "yìdiǎnr")).toEqual(["一:yì", "点儿:diǎnr"]);
    expect(columns("哪儿", "nǎr")).toEqual(["哪儿:nǎr"]);
  });

  it("refuses rather than guess when the two do not pair", () => {
    expect(columns("卡拉OK", "kǎ lā ōu kèi")).toBeUndefined();
    expect(columns("图书馆", "tú shū")).toBeUndefined();
    expect(columns("图书", "tú shū guǎn")).toBeUndefined();
  });
});

describe("pinyinSearchForms", () => {
  it("offers marked, numbered and toneless spellings", () => {
    const forms = pinyinSearchForms("tú shū guǎn");
    expect(forms).toEqual(expect.arrayContaining(["tú shū guǎn", "tu2 shu1 guan3", "tu shu guan", "tushuguan"]));
    expect(pinyinSearchForms("nǚ'ér")).toEqual(expect.arrayContaining(["nv3 er2", "nuer", "nüer"]));
    expect(pinyinSearchForms("yìdiǎnr")).toEqual(expect.arrayContaining(["yi4 dian3 r5", "yidianr"]));
  });
});

describe("isMandarin", () => {
  it("is every Chinese tag but Cantonese", () => {
    expect(isMandarin("zh-Hans")).toBe(true);
    expect(isMandarin("zh-Hant-TW")).toBe(true);
    expect(isMandarin("cmn")).toBe(true);
    expect(isMandarin("zh-yue")).toBe(false);
    expect(isMandarin("yue-Hant")).toBe(false);
    expect(isMandarin("es")).toBe(false);
  });
});

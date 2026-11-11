/**
 * Numbered pinyin as it is actually written: `Fang1 shan1 Xian4` → `Fāng shān Xiàn`.
 *
 * CC-CEDICT and CC-Canto store the tone as a trailing digit because their format is one line of
 * ASCII, and every reader is expected to render it. Acervo shows the reading directly under the
 * headword, in the same place a learner reads it, so leaving the digits there hands them the
 * storage format instead of the word.
 *
 * Deliberately not a transliterator and deliberately not a word segmenter: syllables stay separated
 * exactly as the source separated them, because CC-CEDICT does not record where words begin and
 * joining them would be a guess. Anything that is not recognisably a numbered syllable is returned
 * untouched, so a reading that was already accented, or was never pinyin at all, passes through.
 */

/** Vowels in tone order 1–4; a neutral tone (5, or 0) carries no mark. */
const MARKS: Record<string, string[]> = {
  a: ["ā", "á", "ǎ", "à"], e: ["ē", "é", "ě", "è"], i: ["ī", "í", "ǐ", "ì"],
  o: ["ō", "ó", "ǒ", "ò"], u: ["ū", "ú", "ǔ", "ù"], "ü": ["ǖ", "ǘ", "ǚ", "ǜ"]
};

/** Letters a syllable may be built from, once `u:`/`v` have become `ü`. */
const SYLLABLE = /^([a-zü]+)([0-5])$/i;

/**
 * Where the mark goes.
 *
 * The standard rule, and it is short: `a` or `e` takes it whenever present; `ou` puts it on the
 * `o`; otherwise it lands on the last vowel of the syllable.
 */
function markPosition(letters: string): number {
  const lower = letters.toLowerCase();
  for (const vowel of ["a", "e"]) {
    const at = lower.indexOf(vowel);
    if (at >= 0) return at;
  }
  const ou = lower.indexOf("ou");
  if (ou >= 0) return ou;
  for (let index = lower.length - 1; index >= 0; index -= 1) {
    if (MARKS[lower[index]]) return index;
  }
  return -1;
}

function accentSyllable(token: string): string {
  // `u:` and `v` are both how an ASCII format spells `ü`; CC-CEDICT uses the first, learners the
  // second. `ü` only ever follows n, l, j, q, x or y, which is what keeps this off ordinary Latin.
  const normalised = token.replace(/u:/gi, "ü").replace(/([nljqxy])v/gi, "$1ü");
  const parts = SYLLABLE.exec(normalised);
  if (!parts) return token;
  const [, letters, tone] = parts;
  if (tone === "0" || tone === "5") return letters;
  const at = markPosition(letters);
  if (at < 0) return letters;
  const vowel = letters[at];
  const marked = MARKS[vowel.toLowerCase()]?.[Number(tone) - 1];
  if (!marked) return letters;
  return letters.slice(0, at)
    + (vowel === vowel.toUpperCase() && vowel !== vowel.toLowerCase() ? marked.toUpperCase() : marked)
    + letters.slice(at + 1);
}

/** True when this reads as numbered pinyin rather than as something else entirely. */
export function isNumberedPinyin(reading: string): boolean {
  const tokens = reading.trim().split(/\s+/).filter(Boolean);
  if (!tokens.length) return false;
  const syllables = tokens.filter((token) => SYLLABLE.test(token.replace(/u:/gi, "ü")));
  // Most of it, not all: a reading may carry a stray `·` or a Latin abbreviation between syllables.
  return syllables.length > 0 && syllables.length >= tokens.length - 1;
}

export function accentedPinyin(reading: string): string {
  if (!isNumberedPinyin(reading)) return reading;
  return reading.trim().split(/(\s+)/).map((part) => /\s/.test(part) ? part : accentSyllable(part)).join("");
}

/* ── a reading as syllables with tones ─────────────────────────────────── */

export type Tone = 1 | 2 | 3 | 4 | 5;

/** One syllable of a Mandarin reading, as it is shown: tone-marked, with the tone it carries. */
export interface Syllable {
  /** Tone-marked, in the case it was written: `Běi`, `diǎnr`. */
  text: string;
  /** 1–4, or 5 for the neutral tone, which carries no mark. */
  tone: Tone;
  /** Ends in the `r` that 儿 adds to the syllable before it (`diǎnr`, 点儿). */
  erhua: boolean;
  /** What separated it from the syllable before it in the source: a space, an apostrophe, nothing. */
  before: string;
}

/**
 * Every syllable Hanyu Pinyin has, without tones: what a run like `túshūguǎn` is cut against.
 *
 * Interjections with no vowel (`m`, `ng`, `hm`) are left out: no vocabulary word is spelled with
 * one, and letting them in would let `n` and `m` split ordinary syllables.
 */
const INVENTORY = new Set((
  "a o e ai ei ao ou an en ang eng er yi ya yo ye yao you yan yin yang ying yong "
  + "wu wa wo wai wei wan wen wang weng yu yue yuan yun "
  + "ba bo bai bei bao ban ben bang beng bi bie biao bian bin bing bu "
  + "pa po pai pei pao pou pan pen pang peng pi pie piao pian pin ping pu "
  + "ma mo me mai mei mao mou man men mang meng mi mie miao miu mian min ming mu "
  + "fa fo fei fou fan fen fang feng fu "
  + "da de dai dei dao dou dan den dang deng dong di dia die diao diu dian ding du duo dui duan dun "
  + "ta te tai tei tao tou tan tang teng tong ti tie tiao tian ting tu tuo tui tuan tun "
  + "na ne nai nei nao nou nan nen nang neng nong ni nie niao niu nian nin niang ning nu nuo nuan nü nüe "
  + "la lo le lai lei lao lou lan lang leng long li lia lie liao liu lian lin liang ling lu luo luan lun lü lüe "
  + "ga ge gai gei gao gou gan gen gang geng gong gu gua guo guai gui guan gun guang "
  + "ka ke kai kei kao kou kan ken kang keng kong ku kua kuo kuai kui kuan kun kuang "
  + "ha he hai hei hao hou han hen hang heng hong hu hua huo huai hui huan hun huang "
  + "ji jia jie jiao jiu jian jin jiang jing jiong ju jue juan jun "
  + "qi qia qie qiao qiu qian qin qiang qing qiong qu que quan qun "
  + "xi xia xie xiao xiu xian xin xiang xing xiong xu xue xuan xun "
  + "zha zhe zhi zhai zhei zhao zhou zhan zhen zhang zheng zhong zhu zhua zhuo zhuai zhui zhuan zhun zhuang "
  + "cha che chi chai chao chou chan chen chang cheng chong chu chua chuo chuai chui chuan chun chuang "
  + "sha she shi shai shei shao shou shan shen shang sheng shu shua shuo shuai shui shuan shun shuang "
  + "re ri rao rou ran ren rang reng rong ru rua ruo rui ruan run "
  + "za ze zi zai zei zao zou zan zen zang zeng zong zu zuo zui zuan zun "
  + "ca ce ci cai cao cou can cen cang ceng cong cu cuo cui cuan cun "
  + "sa se si sai sao sou san sen sang seng song su suo sui suan sun"
).split(" "));

/** The longest syllable (`zhuang`), plus the `r` of erhua. */
const LONGEST = 7;

/** A marked vowel → its bare vowel and tone, in both cases. */
const UNMARK = new Map<string, { vowel: string; tone: Tone }>();
for (const [vowel, marked] of Object.entries(MARKS)) {
  marked.forEach((character, index) => {
    UNMARK.set(character, { vowel, tone: (index + 1) as Tone });
    UNMARK.set(character.toUpperCase(), { vowel: vowel.toUpperCase(), tone: (index + 1) as Tone });
  });
}

/** The syllable without its mark, and the tone the mark said; `null` tone when it had none. */
function unmark(text: string): { bare: string; tone: Tone | null; marks: number } {
  let tone: Tone | null = null;
  let marks = 0;
  let bare = "";
  for (const character of text) {
    const found = UNMARK.get(character);
    if (found) { tone = found.tone; marks += 1; bare += found.vowel; } else bare += character;
  }
  return { bare, tone, marks };
}

/** A bare syllable (any case) is one Pinyin has, or one with the `r` of erhua after it. */
function syllableShape(bare: string): { erhua: boolean } | null {
  const lower = bare.toLowerCase();
  if (INVENTORY.has(lower)) return { erhua: false };
  if (lower.endsWith("r") && INVENTORY.has(lower.slice(0, -1)) && lower !== "err") return { erhua: true };
  return null;
}

/**
 * Cuts one run of tone-marked letters into syllables: `túshūguǎn` → `tú`, `shū`, `guǎn`.
 *
 * Longest match first, backing off when the rest will not cut. One mark per syllable is the rule that
 * settles most ambiguity a toneless table leaves (`xīān` is `xī` + `ān`, not `xiān`), and erhua is
 * allowed only at the end of a run, where Pinyin writes it.
 */
function cutRun(run: string): { text: string; tone: Tone | null; erhua: boolean }[] | null {
  const characters = Array.from(run);
  const cut = (from: number): { text: string; tone: Tone | null; erhua: boolean }[] | null => {
    if (from === characters.length) return [];
    for (let length = Math.min(LONGEST, characters.length - from); length > 0; length -= 1) {
      const text = characters.slice(from, from + length).join("");
      const { bare, tone, marks } = unmark(text);
      if (marks > 1) continue;
      const shape = syllableShape(bare);
      if (!shape || (shape.erhua && from + length !== characters.length)) continue;
      const rest = cut(from + length);
      if (rest) return [{ text, tone, erhua: shape.erhua }, ...rest];
    }
    return null;
  };
  return cut(0);
}

/**
 * A Mandarin reading as syllables with tones, from numbered or tone-marked Pinyin alike.
 *
 * `tu2 shu1 guan3`, `tú shū guǎn` and `túshūguǎn` give the same three syllables. CC-CEDICT's `r5`
 * (the 儿 of 一点儿) joins the syllable before it. `null` when the reading does not read as Pinyin,
 * or when it carries no tone at all — a reading with no marks is not one whose tones are neutral.
 */
export function pinyinSyllables(reading: string): Syllable[] | null {
  const source = reading.normalize("NFC").trim();
  if (!source) return null;
  const syllables: Syllable[] = [];
  let toned = false;
  const pieces = source.split(/([\s'’\-]+)/);
  let gap = "";
  for (const piece of pieces) {
    if (!piece) continue;
    if (/^[\s'’\-]+$/.test(piece)) { gap += piece.replace(/\s+/g, " ").replace(/’/g, "'"); continue; }
    const before = syllables.length ? gap : "";
    gap = "";
    if (/\d/.test(piece)) {
      // Numbered: each syllable carries its digit; a run may hold several (`tu2shu1`).
      const ascii = piece.replace(/u:/gi, "ü").replace(/v/gi, "ü");
      const parts = ascii.match(/[a-zü]+[0-5]|./gi) ?? [];
      let first = true;
      for (const part of parts) {
        const numbered = /^([a-zü]+)([0-5])$/i.exec(part);
        if (!numbered) return null;
        // After j, q, x and y the dots are never written: `ju`, not `jü`.
        const letters = numbered[1].replace(/^([jqxy])ü/i, "$1u");
        const digit = numbered[2];
        const tone = (digit === "0" ? 5 : Number(digit)) as Tone;
        if (letters.toLowerCase() === "r" && syllables.length) {
          const previous = syllables[syllables.length - 1];
          syllables[syllables.length - 1] = { ...previous, text: `${previous.text}r`, erhua: true };
          first = false;
          continue;
        }
        const shape = syllableShape(letters);
        if (!shape) return null;
        if (tone !== 5) toned = true;
        syllables.push({ text: accentSyllable(`${letters}${tone}`), tone, erhua: shape.erhua, before: first ? before : "" });
        first = false;
      }
      continue;
    }
    if (!/^[\p{L}]+$/u.test(piece)) return null;
    const cut = cutRun(piece);
    if (!cut) return null;
    cut.forEach((syllable, index) => {
      if (syllable.tone) toned = true;
      syllables.push({ text: syllable.text, tone: syllable.tone ?? 5, erhua: syllable.erhua, before: index === 0 ? before : "" });
    });
  }
  return toned && syllables.length ? syllables : null;
}

/** One column of a headword: the characters one syllable reads, and that syllable. */
export interface HanziColumn {
  characters: string;
  syllable: Syllable;
}

const HAN = /^\p{Script=Han}$/u;

/**
 * Pairs each Han character of a headword with the syllable that reads it: 图书馆 with `tú shū guǎn`.
 *
 * One character, one syllable, except that a syllable written with erhua also takes the 儿 after it.
 * `null` the moment the two do not pair — a Latin letter in the word (卡拉OK), a count that differs —
 * and the reading is then shown as a line instead: a column that guessed would teach a wrong tone.
 */
export function alignHanzi(headword: string, syllables: readonly Syllable[]): HanziColumn[] | null {
  const characters = Array.from(headword.normalize("NFC").trim());
  const columns: HanziColumn[] = [];
  let at = 0;
  for (const syllable of syllables) {
    const character = characters[at];
    if (!character || !HAN.test(character)) return null;
    if (syllable.erhua && characters[at + 1] === "儿") {
      columns.push({ characters: character + "儿", syllable });
      at += 2;
    } else {
      columns.push({ characters: character, syllable });
      at += 1;
    }
  }
  return at === characters.length && columns.length ? columns : null;
}

/**
 * Every way someone might type a reading into search: as marked, numbered, and with no tones at all,
 * spaced or run together. `tú shū guǎn` → `tu2 shu1 guan3`, `tu shu guan`, `tushuguan`.
 */
export function pinyinSearchForms(reading: string): string[] {
  const syllables = pinyinSyllables(reading);
  if (!syllables) return [];
  const bare = syllables.map((syllable) => unmark(syllable.text).bare.toLowerCase());
  const forms = [
    syllables.map((syllable) => syllable.text.toLowerCase()).join(" "),
    syllables.map((syllable, index) => bare[index].replace(/r$/, syllable.erhua ? "" : "r") + syllable.tone
      + (syllable.erhua ? " r5" : "")).join(" "),
    bare.join(" "),
    bare.join("")
  ];
  // ü is typed as `v` or as plain `u` by anyone without the key.
  const typed = forms.flatMap((form) => form.includes("ü") ? [form, form.replace(/ü/g, "v"), form.replace(/ü/g, "u")] : [form]);
  return [...new Set(typed)];
}

/**
 * The same, for the readings CC-CEDICT writes inside a definition.
 *
 * `涼山彝族自治州|凉山彝族自治州[Liang2 shan1 Yi2 zu2 Zi4 zhi4 zhou1]` is a cross-reference to
 * another entry, and the bracket is the only part of it a reader can be expected to sound out.
 */
export function accentedPinyinInText(value: string): string {
  return value.replace(/\[([^\]]{1,120})\]/g, (whole, inner: string) => {
    // Some CC-CEDICT builds space out the `u:` that stands for `ü`, so `[Lu:3 …]` arrives as
    // `[Lu : 3 …]` and stops looking like pinyin at all. Closing that up costs nothing anywhere
    // else: an IPA bracket has no digit after a letter and still fails the test below.
    const candidate = inner.replace(/\s*:\s*/g, ":");
    return isNumberedPinyin(candidate) ? `[${accentedPinyin(candidate)}]` : whole;
  });
}

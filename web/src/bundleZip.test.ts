import { describe, expect, it } from "vitest";
import { strToU8, zipSync } from "fflate";
import { bundleArchive } from "./bundleZip";

const picture = new Uint8Array([0x52, 0x49, 0x46, 0x46, 1, 2, 3]);
const clip = new Uint8Array([0x4f, 0x67, 0x67, 0x53, 4, 5]);

describe("reading a bundle's archive", () => {
  it("keeps pictures and clips as bytes and everything else as text", () => {
    const archive = bundleArchive("acervo-es.zip", zipSync({
      "acervo.yaml": strToU8("format: acervo-export/1\n"),
      "es/picar.yaml": strToU8("headword: picar\n"),
      "media/es/picar-1.webp": picture,
      "audio/es/picar/headword.ogg": clip,
      "audio/es/picar/clips.yaml": strToU8("- file: headword.ogg\n")
    }));
    expect(archive.files.map((file) => file.path).sort())
      .toEqual(["acervo.yaml", "audio/es/picar/clips.yaml", "es/picar.yaml"]);
    expect([...archive.pictures.keys()]).toEqual(["media/es/picar-1.webp"]);
    expect([...archive.recordings.keys()]).toEqual(["audio/es/picar/headword.ogg"]);
  });

  it("keeps the pictures of a bundle zipped again inside a folder", () => {
    const archive = bundleArchive("again.zip", zipSync({
      "acervo-es/acervo.yaml": strToU8("format: acervo-export/1\n"),
      "acervo-es/media/es/picar-1.webp": picture,
      "acervo-es/audio/es/picar/headword.ogg": clip,
      "__MACOSX/acervo-es/._acervo.yaml": strToU8("noise")
    }));
    expect(archive.files.map((file) => file.path)).toEqual(["acervo-es/acervo.yaml"]);
    expect(archive.pictures.get("acervo-es/media/es/picar-1.webp")).toEqual(picture);
    expect(archive.recordings.size).toBe(1);
  });

  it("reads a lone YAML file as one word document", () => {
    const archive = bundleArchive("picar.yaml", strToU8("headword: picar\n"));
    expect(archive.files).toEqual([{ path: "picar.yaml", text: "headword: picar\n" }]);
  });

  it("keeps file names in any script", () => {
    const archive = bundleArchive("ko.zip", zipSync({ "ko/약하다.yaml": strToU8("headword: 약하다\n") }));
    expect(archive.files[0].path).toBe("ko/약하다.yaml");
  });
});

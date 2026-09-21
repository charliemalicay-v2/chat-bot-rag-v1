import { describe, expect, it } from "vitest";

import { cleanSnippet, relevance } from "./SourcesList";

describe("cleanSnippet", () => {
  it("removes markdown heading markers but keeps the words", () => {
    expect(cleanSnippet("# Tent Care ## Setting up and taking down Choose a flat spot")).toBe(
      "Tent Care Setting up and taking down Choose a flat spot",
    );
  });

  it("leaves hashes that are not headings alone", () => {
    expect(cleanSnippet("Item #5 costs C#")).toBe("Item #5 costs C#");
  });
});

describe("relevance", () => {
  it("turns cosine distance into a percentage, clamped to 0-100", () => {
    expect(relevance(0)).toBe(100);
    expect(relevance(0.19)).toBe(81);
    expect(relevance(1)).toBe(0);
    expect(relevance(1.7)).toBe(0);
    expect(relevance(-0.2)).toBe(100);
  });
});

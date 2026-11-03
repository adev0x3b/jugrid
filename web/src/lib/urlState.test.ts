import { describe, expect, it } from "vitest";
import { ALL_KINDS, parse, serialize } from "./urlState";

describe("map state in the address", () => {
  it("defaults to today's overall risk for every asset", () => {
    expect(parse("")).toEqual({
      scenario: "baseline",
      view: "overall",
      kinds: ALL_KINDS,
      asset: null,
      grid: false,
      raw: false,
    });
    expect(serialize(parse(""))).toBe("");
  });

  it("round-trips a shared link", () => {
    const search = "?scenario=ssp585_2050&view=wind&kinds=line%2Cminor_line&asset=42&grid=1&raw=1";
    const state = parse(search);
    expect(state).toEqual({
      scenario: "ssp585_2050",
      view: "wind",
      kinds: ["line", "minor_line"],
      asset: 42,
      grid: true,
      raw: true,
    });
    expect(serialize(state)).toBe(search);
  });

  it("ignores values it does not know", () => {
    const state = parse("?scenario=ssp126&view=hail&kinds=pylon&asset=-3");
    expect(state.scenario).toBe("baseline");
    expect(state.view).toBe("overall");
    expect(state.kinds).toEqual(ALL_KINDS);
    expect(state.asset).toBeNull();
  });
});

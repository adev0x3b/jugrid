import { describe, expect, it } from "vitest";
import { formatChange, formatKm, formatKv, formatValue } from "./format";
import { levelOf } from "./levels";

describe("formatting", () => {
  it("writes values with their unit, or says there is no data", () => {
    expect(formatValue(12.345, "days/yr")).toBe("12.3 days/yr");
    expect(formatValue(null, "mm")).toBe("No data");
  });

  it("rounds long distances to whole kilometres", () => {
    expect(formatKm(3.14)).toBe("3.1 km");
    expect(formatKm(1234.5)).toBe("1,235 km");
  });

  it("shows voltage in kV", () => {
    expect(formatKv(380)).toBe("380 kV");
    expect(formatKv(null)).toBeNull();
  });

  it("signs score changes in points out of 100", () => {
    expect(formatChange(0.123)).toBe("+12");
    expect(formatChange(-0.03)).toBe("−3");
    expect(formatChange(0.001)).toBe("±0");
    expect(formatChange(null)).toBe("");
  });
});

describe("levels", () => {
  it.each([
    [0, "low"],
    [0.2499, "low"],
    [0.25, "medium"],
    [0.5, "high"],
    [0.75, "very_high"],
    [1, "very_high"],
    [null, null],
  ])("score %s is %s, as the server bands it", (score, level) => {
    expect(levelOf(score)).toBe(level);
  });
});

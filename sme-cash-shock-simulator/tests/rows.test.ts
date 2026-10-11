import { describe, expect, it } from "vitest";
import { validateScenario } from "../src/model/types";
import { loadNearEdge, loadSample, withFields } from "./helpers";

// The Controls build rows by editing a copy of the scenario; these check that what they build is valid
// and that removing something still in use is refused with a message naming it.
describe("adding and removing rows", () => {
  it("a new customer, order line and supplier bill (the Controls' template values) validate", () => {
    const s = withFields(loadNearEdge(), (c) => {
      c.customers.push({
        id: "C1", name: "New customer C1", keyClient: false, meanDaysToPay: 30, dueDays: 30, earlyPayDiscount: null,
        offerAcceptance: { alpha: 1, beta: 1 }, orderCycleDays: 30, firstOrderDay: 30, orders: [],
      });
      c.customers[0].orders.push({ item: "New item", unitPrice: 100, qtyPerCycle: 1 });
      c.payables.push({ id: "AP-1", label: "New bill AP-1", amount: 1000, dueDay: 30, affectsProfit: true, earlyPayDiscount: null });
    });
    expect(() => validateScenario(s)).not.toThrow();
  });
  it("removing a customer that a receivable uses is refused, naming the field", () => {
    const s = withFields(loadSample(), (c) => void c.customers.splice(2, 1)); // Firm C
    expect(() => validateScenario(s)).toThrow(/receivables\.2\.customerId/);
  });
  it("removing a bill that a decision uses is refused, naming the field", () => {
    const s = withFields(loadSample(), (c) => void c.payables.splice(1, 1)); // inventory
    expect(() => validateScenario(s)).toThrow(/targetId/);
  });
  it("shock announced after it is due is refused (the only link between the two)", () => {
    const s = withFields(loadNearEdge(), (c) => {
      c.shocks[0].announceDay = 30;
      c.shocks[0].dueDay = 25;
    });
    expect(() => validateScenario(s)).toThrow(/announceDay/);
    const ok = withFields(loadNearEdge(), (c) => {
      c.shocks[0].announceDay = 25;
      c.shocks[0].dueDay = 25;
    });
    expect(() => validateScenario(ok)).not.toThrow();
  });
});

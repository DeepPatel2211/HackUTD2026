/** Operator roster and system assignments.
 *
 * This is demonstration data held in the browser. Nothing here is persisted and
 * no pager is really sent -- the backend has no concept of staffing, and the
 * EOG dataset carries no personnel records. Operators are numbered in the order
 * the systems appear, so operator 1 covers the first system, operator 2 the
 * second, and so on, which keeps it correct for an unseen network too.
 */

export type Operator = {
  id: number;
  name: string;
  pager: string;
  role: string;
};

const NAMES = [
  "A. Okafor",
  "M. Castellanos",
  "J. Lindqvist",
  "R. Banerjee",
  "T. Whitfield",
  "S. Nakamura",
  "D. Mwangi",
  "K. Petrova",
  "L. Fontaine",
  "C. Alvarez",
  "N. Haddad",
  "P. Sorensen",
];

/** One operator per system, numbered from 1 in system order. */
export function roster(systemIds: string[]): Operator[] {
  return systemIds.map((_, index) => ({
    id: index + 1,
    name: NAMES[index % NAMES.length],
    pager: `555-0${String(140 + index)}`,
    role: index === 0 ? "Lead night operator" : "Night operator",
  }));
}

/** The default mapping: operator 1 to the first system, 2 to the second. */
export function defaultAssignments(systemIds: string[]): Record<string, number> {
  return Object.fromEntries(systemIds.map((id, index) => [id, index + 1]));
}

export function operatorById(
  people: Operator[],
  id: number | undefined,
): Operator | undefined {
  return people.find((person) => person.id === id);
}

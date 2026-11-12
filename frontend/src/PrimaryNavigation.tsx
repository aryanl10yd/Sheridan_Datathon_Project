type Section = "historical" | "investigation" | "correlations" | "mission";

const sections: [Section, string][] = [
  ["historical", "Historical Activity"],
  ["investigation", "Storm Investigation"],
  ["correlations", "Solar Wind Correlations"],
  ["mission", "Mission Control"],
];

export function PrimaryNavigation({ activeSection, onSelect }: { activeSection: Section; onSelect: (section: Section) => void }) {
  return <nav aria-label="Primary navigation">{sections.map(([id, label]) => <button className={activeSection === id ? "active" : ""} aria-current={activeSection === id ? "page" : undefined} key={id} onClick={() => onSelect(id)}>{label}</button>)}</nav>;
}

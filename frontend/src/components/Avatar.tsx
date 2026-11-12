import employee from "../assets/avatars/employee.jpg";
import manager from "../assets/avatars/manager.jpg";

/* Photos by persona id (Unsplash, free licence; credited in docs/DEMO.md). Unknown ids fall back to initials. */
const PHOTOS: Record<string, string> = { employee, manager };

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
}

export function Avatar({ name, personaId, size = 40 }: { name: string; personaId?: string; size?: number }) {
  const photo = personaId ? PHOTOS[personaId] : undefined;
  if (photo) {
    return <img alt="" src={photo} width={size} height={size} className="shrink-0 rounded-full bg-blue-soft object-cover" style={{ width: size, height: size }} />;
  }
  return (
    <span
      aria-hidden
      className="grid shrink-0 place-items-center rounded-full bg-blue-soft font-semibold text-blue"
      style={{ width: size, height: size, fontSize: size * 0.36 }}
    >
      {initials(name)}
    </span>
  );
}

function initials(name: string): string {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
}

export function Avatar({ name, size = 40 }: { name: string; size?: number }) {
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

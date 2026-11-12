import type { Persona } from "./types";

export const personaLabel = (p: Persona) => `${p.name}, ${p.title}`;

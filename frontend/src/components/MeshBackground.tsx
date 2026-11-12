/* Soft drifting colour behind the app frame. Blob classes and keyframes live in index.css (.mesh). */
export function MeshBackground() {
  return (
    <div data-testid="mesh" aria-hidden className="mesh">
      <i className="b0" /><i className="b4" /><i className="b1" /><i className="b2" /><i className="b3" />
    </div>
  );
}

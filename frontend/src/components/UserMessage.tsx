export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      {/* The one intentional exception to the shape rule: the tail corner (rounded-br-[6px]) marks the speaker. */}
      <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-card rounded-br-[6px] bg-blue px-4 py-2.5 text-white">{text}</p>
    </div>
  );
}

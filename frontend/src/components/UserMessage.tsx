export function UserMessage({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-card rounded-br-[6px] bg-blue px-4 py-2.5 text-white">{text}</p>
    </div>
  );
}

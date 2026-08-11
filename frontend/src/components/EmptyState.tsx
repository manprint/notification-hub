export default function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state" role="status" aria-live="polite">
      {message}
    </div>
  );
}

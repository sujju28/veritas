import { statusLabel, statusTag, type StatusTag } from "./status";

export function StatusTagView({ value }: { value: string | null | undefined }) {
  const tag: StatusTag = statusTag(value);
  return (
    <span className={`tag tag-${tag.toLowerCase()}`} role="status" aria-label={statusLabel(tag)}>
      {statusLabel(tag)}
    </span>
  );
}

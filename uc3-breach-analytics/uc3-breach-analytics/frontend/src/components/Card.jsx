export default function Card({ children, interactive = true, className = "" }) {
  return <div className={`dfz-card ${interactive ? "dfz-card--interactive" : ""} ${className}`}>{children}</div>;
}

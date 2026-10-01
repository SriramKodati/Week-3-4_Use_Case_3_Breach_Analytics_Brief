export default function Button({ children, variant = "primary", icon: Icon, disabled, type = "button", onClick }) {
  return (
    <button type={type} onClick={onClick} disabled={disabled} className={`dfz-button dfz-button--${variant}`}>
      {Icon && <Icon size={16} strokeWidth={1.75} />}
      <span>{children}</span>
    </button>
  );
}

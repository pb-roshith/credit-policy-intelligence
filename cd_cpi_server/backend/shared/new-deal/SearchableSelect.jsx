import React, { useId, useRef, useState } from "react";

export default function SearchableSelect({ value, options, onChange, placeholder, searchPlaceholder, disabled, loading, inputId, allowCustom = false }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const id = useId();
  const trigger = useRef(null);
  const selected = options.find(option => option.value === value);
  const filtered = options.filter(option => `${option.label} ${option.search || ""}`.toLowerCase().includes(query.toLowerCase()));
  if (allowCustom && query.trim() && !options.some(option => option.value.toLowerCase() === query.trim().toLowerCase())) {
    filtered.push({ value: query.trim(), label: query.trim(), description: "Use this legal name" });
  }
  const choose = option => { onChange(option.value); setOpen(false); trigger.current?.focus(); };
  return <div className="shared-deal-picker" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }}>
    <button id={inputId} ref={trigger} type="button" className="shared-picker-trigger" role="combobox" aria-label={placeholder}
      aria-haspopup="listbox" aria-expanded={open} aria-controls={id} disabled={disabled || loading}
      onClick={() => { setOpen(!open); setQuery(""); setActive(0); }}>
      <span>{loading ? "Loading companies…" : selected?.label || value || placeholder}</span><span aria-hidden="true">⌄</span>
    </button>
    {open && <div className="shared-picker-menu">
      <input autoFocus type="search" maxLength={allowCustom ? 256 : undefined} aria-label={searchPlaceholder} placeholder={searchPlaceholder} value={query}
        aria-controls={id} aria-activedescendant={filtered.length ? `${id}-${Math.min(active, filtered.length - 1)}` : undefined}
        onChange={event => { setQuery(event.target.value); setActive(0); }}
        onKeyDown={event => {
          if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
          if (event.key === "ArrowDown") { event.preventDefault(); setActive(index => Math.max(0, Math.min(index + 1, filtered.length - 1))); }
          if (event.key === "ArrowUp") { event.preventDefault(); setActive(index => Math.max(0, index - 1)); }
          if (event.key === "Enter") { event.preventDefault(); if (filtered[active]) choose(filtered[active]); }
        }} />
      <div id={id} role="listbox" aria-label={placeholder} className="shared-picker-options">
        {!filtered.length && <p>No matches found.</p>}
        {filtered.map((option, index) => <button key={option.value} id={`${id}-${index}`} type="button" role="option"
          aria-selected={value === option.value} className={index === active ? "shared-picker-active" : ""}
          onMouseEnter={() => setActive(index)} onClick={() => choose(option)}>
          <span>{option.label}{option.description && <small>{option.description}</small>}</span>
          {value === option.value && <span aria-hidden="true">✓</span>}
        </button>)}
      </div>
    </div>}
  </div>;
}

import { useEffect, useId, useRef, useState } from 'react';

import { Input } from '../../components/ui';
import { useAirports } from './api';

interface Props {
  label: string;
  value: string;
  onChange: (code: string) => void;
  placeholder?: string;
}

/** Airport typeahead. Keyboard-operable: arrows move, Enter selects, Escape closes. */
export function AirportInput({ label, value, onChange, placeholder }: Props) {
  const [text, setText] = useState(value);
  const [debounced, setDebounced] = useState(value);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const listId = useId();
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(text), 200);
    return () => clearTimeout(timer);
  }, [text]);

  useEffect(() => {
    function onClickAway(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClickAway);
    return () => document.removeEventListener('mousedown', onClickAway);
  }, []);

  const { data: airports = [], isFetching } = useAirports(debounced);

  function select(code: string, display: string) {
    onChange(code);
    setText(display);
    setOpen(false);
  }

  return (
    <div ref={containerRef} className="relative">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      <Input
        value={text}
        placeholder={placeholder}
        aria-label={label}
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        role="combobox"
        autoComplete="off"
        onChange={(event) => {
          setText(event.target.value);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (!open || airports.length === 0) return;
          if (event.key === 'ArrowDown') {
            event.preventDefault();
            setActive((index) => Math.min(index + 1, airports.length - 1));
          } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            setActive((index) => Math.max(index - 1, 0));
          } else if (event.key === 'Enter') {
            event.preventDefault();
            const airport = airports[active];
            if (airport) select(airport.iata_code, `${airport.city} (${airport.iata_code})`);
          } else if (event.key === 'Escape') {
            setOpen(false);
          }
        }}
      />

      {open && (airports.length > 0 || isFetching) && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-72 w-full overflow-auto rounded-lg border border-line bg-white shadow-lg"
        >
          {isFetching && airports.length === 0 && (
            <li className="px-3 py-2 text-sm text-muted">Searching…</li>
          )}
          {airports.map((airport, index) => (
            <li key={airport.iata_code} role="option" aria-selected={index === active}>
              <button
                type="button"
                onMouseEnter={() => setActive(index)}
                onClick={() => select(airport.iata_code, `${airport.city} (${airport.iata_code})`)}
                className={`flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left text-sm ${
                  index === active ? 'bg-brand-50' : ''
                }`}
              >
                <span className="truncate">
                  <span className="font-medium">{airport.city}</span>{' '}
                  <span className="text-muted">{airport.name}</span>
                </span>
                <span className="font-mono text-xs text-muted">{airport.iata_code}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

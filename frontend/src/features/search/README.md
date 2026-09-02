# features/search

Finding flights: the search form, the airport typeahead, the results list, and choosing a
flight for every leg of the journey.

## Responsibilities

- Owns: the home search widget, results rendering, sorting, and per-slice selection.
- Does not own: pricing (the API prices every offer) or the booking itself
  (`features/booking`).

## Key objects

| Object | Role |
|---|---|
| [SearchForm.tsx](SearchForm.tsx) | Trip type, route, dates, party, cabin → URL query |
| [AirportInput.tsx](AirportInput.tsx) | Typeahead; arrows move, Enter selects, Escape closes |
| [SearchResultsPage.tsx](SearchResultsPage.tsx) | One section per slice, sorting, selection |
| [FlightCard.tsx](FlightCard.tsx) | One offer; presentational, selection comes from the parent |
| [SelectionBar.tsx](SelectionBar.tsx) | Sticky per-leg summary and the Continue gate |

## Invariants

- **A round trip is one journey, so it is one PNR.** The traveller picks a flight for *every*
  slice before continuing; Continue stays disabled until they have. Booking each leg separately
  would leave someone with an outbound and no way home.
- **Each slice is priced separately and selected separately.** The API answers with one offer
  list per slice, and the booking carries one offer id per slice in travel order.
- **The URL is the search.** Results are rebuilt from the query string, so a link is shareable
  and a refresh does not lose the search.
- **Selection is never colour-only.** The chosen card says `Selected ✓` and carries
  `aria-pressed`; the ring is reinforcement (WCAG 2.2 AA).
- **The bar says what is missing.** A disabled Continue is always accompanied by an `aria-live`
  line naming the leg still to choose.

## Entry points

- `/` — the search widget
- `/search?trip=&from=&to=&depart=&return=&adults=…` — results

## Gotchas

- A one-way search has a single slice and skips the summary bar entirely: selecting goes
  straight to passenger details. Do not "simplify" the two paths into one — the gate only makes
  sense when there is more than one leg.
- Re-selecting a leg replaces just that leg. The wizard store keeps a fixed-length array indexed
  by slice, so `offers[1]` is always the return.
- The offers in the store are the priced, signed ones from the search. They expire in 15 minutes,
  and the passenger form counts down from the *earliest* of them.
- Playwright's `getByRole(name)` matches accessible names by substring, so `'Select'` also
  matches `'Selected ✓'`. Any E2E driver must pass `exact: true`.

## Testing

    make test-fe

Required: Continue is disabled until every leg is chosen and names the missing one; the total
adds up as legs are chosen; re-selecting replaces only that leg; a one-way goes straight on.

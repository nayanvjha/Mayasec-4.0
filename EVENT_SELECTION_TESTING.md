# Event Selection - Testing Checklist

## Manual Testing Guide

### Test 1: Basic Selection
**Steps:**
1. Open console at http://localhost:3000
2. Wait for events to stream
3. Click on first event in stream

**Expected Result:**
- Event row highlights with blue background + right border
- Details panel opens on right
- Details panel shows event data (ID, timestamp, type, IPs, threat score, severity, raw data)
- Header reads "Investigating Event"
- Close button shows "✕"

**Visual Indicators:**
- Event has deeper blue background: `rgba(88, 166, 255, 0.18)`
- Event has right border: `3px solid #58a6ff`
- Details panel has left border: `2px solid #58a6ff`
- Details panel header is bold

---

### Test 2: Toggle Deselection
**Steps:**
1. Select an event (Test 1)
2. Click the same event again

**Expected Result:**
- Event highlight disappears
- Details panel closes
- Back to "Click an event to investigate" message
- Selection state cleared

---

### Test 3: Change Selection
**Steps:**
1. Select event A
2. Verify details show event A's data
3. Click event B

**Expected Result:**
- Event A loses highlight
- Event B gains highlight (blue background + right border)
- Details panel updates to show event B's data
- No flash or flicker during transition
- Selection state changes atomically

---

### Test 4: New Events While Selected
**Steps:**
1. Select event in middle of stream
2. Wait for new events to arrive
3. Observe new events appearing at top

**Expected Result:**
- New events appear at top with 500ms blue glow
- Glow fades after 500ms
- Selected event maintains blue highlight (deeper color)
- Selected event position may shift down as new events arrive
- Selected event ID remains in details panel
- Analyst can compare new event to selected baseline

**Example:**
```
Before:
  Event A (normal)
  Event B (selected) ← Blue highlight, details on right

After New Event:
  Event X (new) ← Glowing blue, will fade
  Event A (normal)
  Event B (selected) ← Still blue highlight, still showing details
```

---

### Test 5: Keyboard Navigation
**Steps:**
1. Press Tab to focus on event row
2. Press Enter to select
3. Verify details panel opens
4. Press Escape (future feature) to close (if implemented)

**Expected Result:**
- Event receives focus (outline or highlight)
- Enter key triggers selection/deselection
- Details panel opens/closes with Enter
- No console errors for keyboard navigation

---

### Test 6: Visual Distinction
**Steps:**
1. Wait for events to arrive
2. Note the new event glow (500ms)
3. While glow is active, select that event
4. Observe both glow and selection highlight

**Expected Result:**
- Can visually distinguish:
  - New arrival: lighter blue glow, inset shadow, fades quickly
  - Selected: deeper blue background, right border, persistent
  - Combination (new + selected): Both effects visible, selected stronger

**CSS Verification:**
```
New event: rgba(88, 166, 255, 0.12)
Selected: rgba(88, 166, 255, 0.18)  ← Deeper
Difference: ~50% more opaque on selected
```

---

### Test 7: Scrolling While Selected
**Steps:**
1. Select an event near bottom of visible list
2. Scroll the event stream
3. Selected event scrolls with stream

**Expected Result:**
- Selected event stays highlighted even as it scrolls out of view
- If scrolls out of viewport: highlight disappears visually but remains in DOM
- If scrolls back into view: highlight reappears
- Details panel continues showing selected event's data
- No lag or performance issues while scrolling

---

### Test 8: Multiple Rapid Selections
**Steps:**
1. Rapidly click different events (5-10 clicks in succession)
2. Verify state updates correctly

**Expected Result:**
- Each click updates selection to new event
- Details panel updates for each new selection
- No ghost selections or stale data
- All state transitions clean and instantaneous
- No console errors

---

### Test 9: Selection Persists Across Re-renders
**Steps:**
1. Select an event
2. Wait and observe stream updating
3. Monitor details panel stays open with same event

**Expected Result:**
- Selection remains active even as:
  - New events arrive
  - Component re-renders
  - Event array grows
  - Array order changes (new events at top)
- Details panel never closes unexpectedly
- Selected event ID remains stable

---

### Test 10: Details Panel Data Accuracy
**Steps:**
1. Select an event
2. Verify each field in details panel:
   - Event ID matches event object
   - Timestamp matches exact format
   - Type matches event_type
   - Source matches source_ip
   - Destination matches destination_ip
   - Threat Score matches threat_score (0-100)
   - Severity matches severity_level
   - Raw Data is valid JSON

**Expected Result:**
- All data displayed accurately
- No data corruption or truncation
- JSON formatting is readable (indented)
- No missing fields
- Special characters rendered correctly

---

### Test 11: Investigation Mode Header
**Steps:**
1. No selection: Check details panel header
2. Select event: Check details panel header

**Expected Result:**
- No selection: "Click an event to investigate"
- With selection: "Investigating Event"
- Header changes dynamically based on state

---

### Test 12: Close Button Functionality
**Steps:**
1. Select an event
2. Click the "✕" close button
3. Verify panel closes

**Expected Result:**
- Close button is visible in header
- Click closes details panel
- Selection is cleared
- "Click an event to investigate" message appears
- Event row loses highlight

---

### Test 13: Responsive Design (Mobile)
**Steps:**
1. Open on mobile (or use Chrome DevTools mobile view)
2. Try selecting event
3. Observe layout changes

**Expected Result:**
- On mobile: Details panel may be hidden or stacked
- Selection still works (event highlighted in stream)
- Can open details if panel is collapsible
- No broken layouts or overflow

---

### Test 14: Error States
**Steps:**
1. Simulate WebSocket disconnect
2. Try selecting event
3. Verify behavior with error message shown

**Expected Result:**
- Selection still works even if WebSocket disconnects
- Error message displays without blocking interaction
- Can still click events and see details

---

### Test 15: Console Errors
**Steps:**
1. Open browser DevTools Console
2. Perform all selections and interactions
3. Watch console for errors

**Expected Result:**
- No JavaScript errors
- No PropType warnings
- No memory leaks (React DevTools)
- Clean console output

---

## Automated Testing (Unit Tests)

### Test: Selection Logic

```javascript
test('toggle selection on same event', () => {
  const event = { event_id: 'evt_123', event_type: 'test' };
  const { rerender } = render(<SOCEventConsole events={[event]} />);
  
  // First click: select
  fireEvent.click(screen.getByRole('button'));
  expect(screen.getByText('Investigating Event')).toBeInTheDocument();
  
  // Second click: deselect
  fireEvent.click(screen.getByRole('button'));
  expect(screen.getByText('Click an event to investigate')).toBeInTheDocument();
});

test('change selection to different event', () => {
  const events = [
    { event_id: 'evt_1', event_type: 'attack_a' },
    { event_id: 'evt_2', event_type: 'attack_b' }
  ];
  render(<SOCEventConsole events={events} />);
  
  // Select first event
  const rows = screen.getAllByRole('button');
  fireEvent.click(rows[0]);
  expect(screen.getByText('attack_a')).toBeInTheDocument();
  
  // Select second event
  fireEvent.click(rows[1]);
  expect(screen.getByText('attack_b')).toBeInTheDocument();
});
```

### Test: Visual Marking

```javascript
test('selected event has selected-event class', () => {
  const event = { event_id: 'evt_123', event_type: 'test' };
  render(<LiveEventStream events={[event]} selectedEventId="evt_123" />);
  
  const row = screen.getByRole('button').parentElement;
  expect(row).toHaveClass('selected-event');
  expect(row).toHaveClass('event-row');
});

test('new event has new-event class only', () => {
  const event = { event_id: 'evt_123', event_type: 'test' };
  render(<LiveEventStream events={[event]} selectedEventId={null} />);
  
  // Wait for highlight
  const row = screen.getByRole('button').parentElement;
  expect(row).toHaveClass('new-event');
  expect(row).not.toHaveClass('selected-event');
});
```

---

## Browser Compatibility

Test on:
- [ ] Chrome 120+
- [ ] Firefox 121+
- [ ] Safari 17+
- [ ] Edge 120+

All modern browsers should support:
- ES6 destructuring
- Optional chaining (`?.`)
- Array methods (map, filter)
- CSS Grid and Flexbox
- CSS custom properties
- Arrow functions
- Template literals

---

## Performance Testing

### Metrics to Monitor

**In React DevTools Profiler:**
- Selection click render time: <50ms
- Details panel update: <30ms
- Event row class update: <10ms
- Memory footprint with 100+ events: <5MB

**In Chrome DevTools:**
- No layout thrashing
- No forced reflows
- Smooth 60fps scrolling
- Selection state changes instant

---

## Data Flow Verification

**Expected Flow:**
```
1. Analyst clicks event row
   └─ onClick fires: onEventSelect(event, isSelected)

2. LiveEventStream calls callback
   └─ Callback propagates to parent (SOCEventConsole)

3. SOCEventConsole.handleEventSelect executes
   └─ setSelectedEvent(event) or setSelectedEvent(null)

4. State updates trigger re-render
   └─ selectedEvent in state changes

5. LiveEventStream receives new prop
   └─ selectedEventId={selectedEvent?.event_id}

6. Event rows re-render with new prop
   └─ isSelected = (eventId === selectedEventId)
   └─ className includes 'selected-event'

7. Details panel sees selectedEvent prop
   └─ Renders event data or "no selection" message

8. CSS applies styling
   └─ .selected-event background/border/shadow visible

9. Analyst sees updates
   └─ Event highlighted, details displayed
```

---

## Constraints Verification

- [ ] No URL changes when selecting (check browser address bar)
- [ ] No page reload when selecting (check Network tab)
- [ ] No modal popup (check DOM for modal elements)
- [ ] Selection persists while scrolling
- [ ] Selection persists while new events arrive
- [ ] New events don't affect selected event ID
- [ ] Multiple selections don't create memory leaks

---

## Regression Testing

Verify existing features still work:
- [ ] New event highlight (500ms glow)
- [ ] Connection status indicator
- [ ] Error message display
- [ ] Event count display
- [ ] Scrolling (no jank)
- [ ] Keyboard accessibility
- [ ] Color-coded severity
- [ ] Threat score display
- [ ] Empty state messaging
- [ ] Event row hover effects

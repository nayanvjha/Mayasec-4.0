import React, { useState, useCallback } from 'react';
import './EventStreamFilters.css';

/**
 * EventStreamFilters
 * 
 * Live filtering controls for SOC Event Stream.
 * Provides real-time filtering without affecting WebSocket stream.
 * 
 * Filters:
 * - Severity (Critical, High, Medium, Low, Info, All)
 * - Event Type (All available types)
 * - Source IP (text input, substring match)
 * - Time Window (Last 5/10/30/60 minutes)
 * 
 * Props:
 * - onFilterChange: (filters) => void - Called when any filter changes
 * - availableEventTypes: string[] - List of event types for dropdown
 */
const EventStreamFilters = ({ onFilterChange, availableEventTypes = [] }) => {
  // Filter state
  const [severity, setSeverity] = useState('ALL');
  const [eventType, setEventType] = useState('ALL');
  const [sourceIp, setSourceIp] = useState('');
  const [timeWindow, setTimeWindow] = useState(30); // minutes

  // Severity options
  const severityOptions = [
    { value: 'ALL', label: 'All Severities' },
    { value: 'CRITICAL', label: 'Critical' },
    { value: 'HIGH', label: 'High' },
    { value: 'MEDIUM', label: 'Medium' },
    { value: 'LOW', label: 'Low' },
    { value: 'INFO', label: 'Info' },
  ];

  // Time window options (in minutes)
  const timeWindowOptions = [
    { value: 5, label: 'Last 5 minutes' },
    { value: 10, label: 'Last 10 minutes' },
    { value: 30, label: 'Last 30 minutes' },
    { value: 60, label: 'Last 60 minutes' },
  ];

  // Event type options with "All" at top
  const eventTypeOptions = [
    { value: 'ALL', label: 'All Event Types' },
    ...availableEventTypes
      .sort()
      .map(type => ({ value: type, label: type }))
  ];

  /**
   * Notify parent of filter changes
   */
  const notifyFilterChange = useCallback((newFilters) => {
    if (onFilterChange) {
      onFilterChange(newFilters);
    }
  }, [onFilterChange]);

  /**
   * Handle severity change
   */
  const handleSeverityChange = (e) => {
    const newSeverity = e.target.value;
    setSeverity(newSeverity);
    notifyFilterChange({
      severity: newSeverity,
      eventType,
      sourceIp,
      timeWindow,
    });
  };

  /**
   * Handle event type change
   */
  const handleEventTypeChange = (e) => {
    const newEventType = e.target.value;
    setEventType(newEventType);
    notifyFilterChange({
      severity,
      eventType: newEventType,
      sourceIp,
      timeWindow,
    });
  };

  /**
   * Handle source IP change
   */
  const handleSourceIpChange = (e) => {
    const newSourceIp = e.target.value;
    setSourceIp(newSourceIp);
    notifyFilterChange({
      severity,
      eventType,
      sourceIp: newSourceIp,
      timeWindow,
    });
  };

  /**
   * Handle time window change
   */
  const handleTimeWindowChange = (e) => {
    const newTimeWindow = parseInt(e.target.value, 10);
    setTimeWindow(newTimeWindow);
    notifyFilterChange({
      severity,
      eventType,
      sourceIp,
      timeWindow: newTimeWindow,
    });
  };

  /**
   * Clear all filters
   */
  const handleClearFilters = () => {
    setSeverity('ALL');
    setEventType('ALL');
    setSourceIp('');
    setTimeWindow(30);
    notifyFilterChange({
      severity: 'ALL',
      eventType: 'ALL',
      sourceIp: '',
      timeWindow: 30,
    });
  };

  /**
   * Check if any filters are active
   */
  const hasActiveFilters = 
    severity !== 'ALL' ||
    eventType !== 'ALL' ||
    sourceIp !== '' ||
    timeWindow !== 30;

  return (
    <div className="event-stream-filters">
      <div className="filters-container">
        {/* Severity Filter */}
        <div className="filter-group">
          <label htmlFor="severity-filter" className="filter-label">
            Severity
          </label>
          <select
            id="severity-filter"
            className="filter-input severity-select"
            value={severity}
            onChange={handleSeverityChange}
            title="Filter by event severity level"
          >
            {severityOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Event Type Filter */}
        <div className="filter-group">
          <label htmlFor="event-type-filter" className="filter-label">
            Event Type
          </label>
          <select
            id="event-type-filter"
            className="filter-input event-type-select"
            value={eventType}
            onChange={handleEventTypeChange}
            title="Filter by event type"
          >
            {eventTypeOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Source IP Filter */}
        <div className="filter-group">
          <label htmlFor="source-ip-filter" className="filter-label">
            Source IP
          </label>
          <input
            id="source-ip-filter"
            type="text"
            className="filter-input source-ip-input"
            placeholder="Enter IP or partial match..."
            value={sourceIp}
            onChange={handleSourceIpChange}
            title="Filter by source IP (supports partial matching)"
          />
        </div>

        {/* Time Window Filter */}
        <div className="filter-group">
          <label htmlFor="time-window-filter" className="filter-label">
            Time Window
          </label>
          <select
            id="time-window-filter"
            className="filter-input time-window-select"
            value={timeWindow}
            onChange={handleTimeWindowChange}
            title="Filter by time window"
          >
            {timeWindowOptions.map(option => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/* Clear Filters Button */}
        {hasActiveFilters && (
          <div className="filter-group clear-button-group">
            <button
              className="clear-filters-btn"
              onClick={handleClearFilters}
              title="Clear all active filters"
            >
              Clear Filters
            </button>
          </div>
        )}
      </div>

      {/* Filter Status */}
      {hasActiveFilters && (
        <div className="filter-status">
          <div className="status-indicator">
            <span className="status-dot"></span>
            <span className="status-text">
              Filters active: 
              {severity !== 'ALL' && ` Severity=${severity}`}
              {eventType !== 'ALL' && `, Type=${eventType}`}
              {sourceIp && `, IP=${sourceIp}`}
              {timeWindow !== 30 && `, Last ${timeWindow}m`}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};

export default EventStreamFilters;

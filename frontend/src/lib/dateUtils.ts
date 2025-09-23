/**
 * Utility functions for handling dates and timezones
 */

/**
 * Format a date/timestamp to local timezone
 * @param dateInput - Date string, timestamp, or Date object
 * @returns Formatted date string in local timezone
 */
export const formatToLocalTime = (
  dateInput: string | number | Date,
): string => {
  let date: Date;

  if (typeof dateInput === "string") {
    // Handle ISO string from backend - if it doesn't end with Z, treat as UTC
    if (
      dateInput.includes("T") &&
      !dateInput.endsWith("Z") &&
      !dateInput.includes("+")
    ) {
      // Assume it's UTC and append Z
      date = new Date(dateInput + "Z");
    } else {
      date = new Date(dateInput);
    }
  } else if (typeof dateInput === "number") {
    // Handle timestamp (should be in milliseconds)
    date = new Date(dateInput);
  } else {
    date = dateInput;
  }

  // Check if date is valid
  if (isNaN(date.getTime())) {
    return "Invalid Date";
  }

  return date.toLocaleString();
};

/**
 * Format a date/timestamp to local timezone with custom format
 * @param dateInput - Date string, timestamp, or Date object
 * @param options - Intl.DateTimeFormatOptions
 * @returns Formatted date string in local timezone
 */
export const formatToLocalTimeWithOptions = (
  dateInput: string | number | Date,
  options: Intl.DateTimeFormatOptions = {},
): string => {
  let date: Date;

  if (typeof dateInput === "string") {
    // Handle ISO string from backend - if it doesn't end with Z, treat as UTC
    if (
      dateInput.includes("T") &&
      !dateInput.endsWith("Z") &&
      !dateInput.includes("+")
    ) {
      // Assume it's UTC and append Z
      date = new Date(dateInput + "Z");
    } else {
      date = new Date(dateInput);
    }
  } else if (typeof dateInput === "number") {
    date = new Date(dateInput);
  } else {
    date = dateInput;
  }

  if (isNaN(date.getTime())) {
    return "Invalid Date";
  }

  return date.toLocaleString(undefined, options);
};

/**
 * Format deployment timestamp specifically
 * @param dateInput - Date string, timestamp, or Date object
 * @returns Formatted date and time string
 */
export const formatDeploymentTime = (
  dateInput: string | number | Date,
): string => {
  return formatToLocalTimeWithOptions(dateInput, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
};

/**
 * Format log timestamp specifically
 * @param dateInput - Date string, timestamp, or Date object
 * @returns Formatted date and time string for logs
 */
export const formatLogTime = (dateInput: string | number | Date): string => {
  return formatToLocalTimeWithOptions(dateInput, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
};

/**
 * Parse deployment logs and convert timestamps to local time
 * @param logs - Raw deployment logs string
 * @returns Processed logs with local timestamps
 */
export const processDeploymentLogs = (logs: string): string => {
  if (!logs) return "";

  // Regular expression to match timestamps in format [2024-01-15T10:30:45.123456]
  const timestampRegex = /\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]/g;

  return logs.replace(timestampRegex, (match, timestamp) => {
    try {
      // Convert UTC timestamp to local time
      const localTime = formatToLocalTimeWithOptions(timestamp, {
        month: "2-digit",
        day: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
      return `[${localTime}]`;
    } catch (error) {
      // If conversion fails, return original timestamp
      return match;
    }
  });
};

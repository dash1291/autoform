# Inline Color Definitions Report

## Summary of Color Usage in Frontend Code

### Modified Files with Inline Colors:

#### 1. `/frontend/src/app/dashboard/page.tsx`
- **Line 74**: `border-blue-600` - Loading spinner
- **Line 99**: `text-gray-400` - Icon color
- **Line 187**: `border-blue-600` - Loading spinner 
- **Line 201**: `text-gray-900` - Heading text
- **Line 210**: `border-gray-800` - Border
- **Line 283**: `border-gray-300`, `focus:ring-blue-500` - Form inputs
- **Line 296**: `border-gray-300`, `focus:ring-blue-500` - Form inputs

#### 2. `/frontend/src/app/page.tsx`
- **Line 42**: `hover:border-gray-800`, `border-gray-600` - Button styles
- **Line 51**: `text-gray-900` - Heading text
- **Line 56-82**: Multiple color classes for feature cards:
  - `bg-orange-50`, `text-orange-600` - AWS Native icon
  - `bg-blue-100`, `text-blue-600` - Fast Deployments icon
  - `bg-purple-100`, `text-purple-600` - Environments icon
- **Line 94**: `border-gray-800` - Border color

#### 3. `/frontend/src/app/projects/[id]/page.tsx`
This file contains the most inline colors:
- **Lines 74, 187, 263**: `border-blue-600` - Loading spinners
- **Lines 201, 253-254, 272-273**: `text-gray-900`, `text-gray-600` - Text colors
- **Lines 275-276**: `bg-blue-600`, `hover:bg-blue-700` - Link styles
- **Lines 294**: `text-blue-600`, `hover:text-blue-700` - Back link
- **Lines 385-402**: Environment status colors:
  - `bg-green-100 text-green-800` - Healthy status
  - `bg-red-100 text-red-800` - Error/Crash loop status
  - `bg-blue-100 text-blue-800` - In progress status
  - `bg-orange-100 text-orange-800` - Degraded status
  - `bg-gray-100 text-gray-800` - Default/No tasks status
  - `bg-gray-100 text-gray-600` - Not deployed status
- **Lines 423**: `text-blue-600 hover:text-blue-700` - Domain links
- **Lines 432-433**: `bg-red-50 border-red-200 text-red-800` - Error alerts
- **Lines 437-447**: `bg-yellow-50 border-yellow-200 text-yellow-800` - Warning alerts
- **Lines 489**: `bg-gray-900 text-green-400` - Terminal/logs display
- **Lines 517-521**: Deployment status badges (same color scheme as environment statuses)
- **Lines 547, 556**: `bg-gray-100` - Code background
- **Lines 590**: `bg-gray-900 text-gray-100` - Logs display
- **Line 657**: `bg-gray-50` - Empty state background
- **Lines 820-874**: Resource display colors:
  - `bg-gray-50` - Resource item backgrounds
  - `text-gray-900`, `text-gray-500` - Text colors

#### 4. `/frontend/src/components/ui/button.tsx`
- **Line 13**: `hover:border-gray-800 border-gray-600` - Default variant border colors

#### 5. `/frontend/src/components/ui/card.tsx`
- No hardcoded colors found (uses CSS variables)

#### 6. `/frontend/src/app/globals.css`
This file contains color-related CSS but uses CSS custom properties for theming:
- **Lines 73-134**: Prose styling with hardcoded colors:
  - `text-gray-700`, `text-gray-900` - Text colors
  - `border-gray-200` - Border colors
  - `text-blue-600`, `hover:text-blue-700` - Link colors
  - `bg-gray-100`, `text-gray-800` - Inline code
  - `bg-gray-900`, `text-gray-100` - Code blocks
  - `border-blue-500`, `bg-blue-50`, `text-blue-700` - Blockquotes

### Other Files with Significant Color Usage:

#### Components with Heavy Color Usage:
1. **SimpleShell.tsx** - Terminal interface colors
2. **LogsViewer.tsx** - Log level colors (error=red, warning=yellow, info=blue)
3. **DeploymentModal.tsx** - Status badge colors
4. **EnvironmentManagement.tsx** - Environment status colors
5. **UserAwsConfiguration.tsx** - AWS config status colors
6. **NetworkConfiguration.tsx** - Network status and info colors
7. **WebhookConfiguration.tsx** - Webhook status colors

### Common Color Patterns:
1. **Status Colors**:
   - Success: `bg-green-100 text-green-800` or `bg-green-50 text-green-700`
   - Error: `bg-red-100 text-red-800` or `bg-red-50 text-red-700`
   - Warning: `bg-yellow-100 text-yellow-800` or `bg-yellow-50 text-yellow-700`
   - Info: `bg-blue-100 text-blue-800` or `bg-blue-50 text-blue-700`
   - In Progress: `bg-blue-100 text-blue-800`
   - Neutral: `bg-gray-100 text-gray-800`

2. **UI Elements**:
   - Loading spinners: `border-blue-600`
   - Text colors: `text-gray-900` (headings), `text-gray-600` (body), `text-gray-500` (muted)
   - Borders: `border-gray-200`, `border-gray-300`, `border-gray-800`
   - Backgrounds: `bg-gray-50` (subtle), `bg-gray-100` (code/highlights)
   - Links: `text-blue-600 hover:text-blue-700`

3. **Terminal/Code Display**:
   - Background: `bg-gray-900`
   - Text: `text-green-400` (terminal), `text-gray-100` (logs)

### Recommendations:
1. Create a consistent color system using CSS variables or Tailwind theme extensions
2. Define semantic color tokens for statuses, alerts, and UI states
3. Centralize color definitions to improve maintainability
4. Consider dark mode support by using color variables that can be swapped
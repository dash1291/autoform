import { cn } from '@/lib/utils'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  color?: 'primary' | 'secondary' | 'white'
  className?: string
}

const sizeClasses = {
  sm: 'h-4 w-4',
  md: 'h-8 w-8',
  lg: 'h-12 w-12'
}

const colorClasses = {
  primary: 'border-secondary',
  secondary: 'border-secondary',
  white: 'border-white'
}

export function Spinner({ size = 'md', color = 'primary', className }: SpinnerProps) {
  return (
    <div
      className={cn(
        'animate-spin rounded-full border-b-2',
        sizeClasses[size],
        colorClasses[color],
        className
      )}
    />
  )
}
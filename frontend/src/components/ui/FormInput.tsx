import { ReactNode } from 'react'

interface FormInputProps {
  id: string
  label: string
  value: string | number
  onChange: (value: string | number) => void
  type?: 'text' | 'number' | 'url' | 'email' | 'password'
  placeholder?: string
  helpText?: string
  required?: boolean
  disabled?: boolean
  className?: string
  inputClassName?: string
  rightElement?: ReactNode
  bottomElement?: ReactNode
}

export function FormInput({
  id,
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
  helpText,
  required = false,
  disabled = false,
  className = '',
  inputClassName = '',
  rightElement,
  bottomElement
}: FormInputProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = type === 'number' ? (parseInt(e.target.value) || 0) : e.target.value
    onChange(newValue)
  }

  const defaultInputClasses = inputClassName || 'bg-popover border-gray-700'

  return (
    <div className={className}>
      <label htmlFor={id} className="block text-sm font mb-2">
        {label}
      </label>
      <div className="relative">
        <input
          type={type}
          id={id}
          value={value}
          onChange={handleChange}
          disabled={disabled}
          className={`w-full text-sm px-3 py-3 border ${defaultInputClasses} rounded focus:ring-blue-500 focus:border-blue-500 disabled:opacity-50 disabled:cursor-not-allowed ${rightElement ? 'pr-10' : ''}`}
          placeholder={placeholder}
          required={required}
        />
        {rightElement && (
          <div className="absolute inset-y-0 right-0 flex items-center pr-3">
            {rightElement}
          </div>
        )}
      </div>
      {bottomElement}
      {helpText && (
        <p className="text-xs text-muted-foreground mt-1">{helpText}</p>
      )}
    </div>
  )
}
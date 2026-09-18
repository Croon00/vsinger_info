export const isMock = import.meta.env.VITE_DATA_MODE === 'mock'
export const capabilities = { birthdays: isMock }

export const BUSINESS_TIME_ZONE = 'Asia/Shanghai'
const formatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BUSINESS_TIME_ZONE,
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})

/** API 时间必须带显式时区；拒绝浏览器按本地时区解释无时区字符串。 */
export function formatBeijingTime(value) {
  if (typeof value !== 'string' || !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    throw new TypeError('时间必须包含时区')
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) throw new RangeError('无效时间')
  const parts = Object.fromEntries(formatter.formatToParts(date).map(p => [p.type, p.value]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}

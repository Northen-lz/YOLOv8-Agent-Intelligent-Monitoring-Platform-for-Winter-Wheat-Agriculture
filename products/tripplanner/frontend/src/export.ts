import type { TripPlan } from './types'

export function downloadJSON(plan: TripPlan) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(plan, null, 2)], { type: 'application/json;charset=utf-8' }))
  download(url, `${plan.request.city}-行程.json`)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function download(url: string, name: string) {
  const a = document.createElement('a'); a.href = url; a.download = name; a.click()
}

export async function exportPlan(format: 'png' | 'pdf', city: string) {
  const { default: html2canvas } = await import('html2canvas')
  // 分块截图再排版，避免把长行程塞进一张 A4，也避免地图跨域 canvas 污染。
  const blocks = Array.from(document.querySelectorAll<HTMLElement>('[data-export-block]'))
  const canvases: HTMLCanvasElement[] = []
  for (const block of blocks) {
    canvases.push(await html2canvas(block, { scale: 1.5, backgroundColor: '#ffffff', useCORS: false,
      onclone: (doc) => {
        doc.querySelectorAll<HTMLElement>('[data-no-export]').forEach(el => el.style.display = 'none')
      } }))
  }
  if (!canvases.length) throw new Error('暂无可导出的行程')
  if (format === 'png') {
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(...canvases.map(c => c.width))
    canvas.height = canvases.reduce((sum, c) => sum + c.height + 24, 24)
    if (canvas.height > 30000) throw new Error('行程图片过长，请改用 PDF 分页导出')
    const ctx = canvas.getContext('2d')!
    ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, canvas.width, canvas.height)
    let y = 24
    for (const c of canvases) { ctx.drawImage(c, 0, y); y += c.height + 24 }
    download(canvas.toDataURL('image/png'), `${city}-行程.png`)
  } else {
    const { jsPDF } = await import('jspdf')
    const pdf = new jsPDF('p', 'mm', 'a4')
    let y = 12
    for (const c of canvases) {
      const width = 186
      const height = c.height * width / c.width
      if (height <= 273) {
        if (y + height > 285) { pdf.addPage(); y = 12 }
        pdf.addImage(c.toDataURL('image/png'), 'PNG', 12, y, width, height, undefined, 'FAST')
        y += height + 5
      } else {
        // 超长的单日编辑结果分片，确保底部不会截断或丢失。
        if (y > 12) { pdf.addPage(); y = 12 }
        const sliceHeight = Math.floor(273 * c.width / width)
        for (let offset = 0; offset < c.height; offset += sliceHeight) {
          if (offset) pdf.addPage()
          const slice = document.createElement('canvas'); slice.width = c.width; slice.height = Math.min(sliceHeight, c.height - offset)
          slice.getContext('2d')!.drawImage(c, 0, offset, c.width, slice.height, 0, 0, c.width, slice.height)
          const h = slice.height * width / slice.width
          pdf.addImage(slice.toDataURL('image/png'), 'PNG', 12, 12, width, h, undefined, 'FAST')
          y = 12 + h + 5
        }
      }
    }
    pdf.save(`${city}-行程.pdf`)
  }
}

export const SIGNATURE_WIDTH = 600
export const SIGNATURE_HEIGHT = 200

export function validSignature(strokes) {
  if (!Array.isArray(strokes) || strokes.length > 100) return false
  let distance = 0, count = 0
  for (const stroke of strokes) {
    if (!Array.isArray(stroke) || !stroke.length) return false
    for (let index = 0; index < stroke.length; index++) {
      const point = stroke[index]
      if (!point || !Number.isFinite(point.x) || !Number.isFinite(point.y) || point.x < 0 || point.x > SIGNATURE_WIDTH || point.y < 0 || point.y > SIGNATURE_HEIGHT || ++count > 10000) return false
      if (index) distance += Math.hypot(point.x - stroke[index - 1].x, point.y - stroke[index - 1].y)
    }
  }
  return count >= 3 && distance >= 15
}

export const signaturePath = stroke => stroke.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(' ')

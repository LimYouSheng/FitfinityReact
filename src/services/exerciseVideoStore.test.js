import { afterEach, expect, it, vi } from 'vitest'
import { loadExerciseVideoBlob, saveExerciseVideoBlob } from './exerciseVideoStore.js'
afterEach(()=>vi.unstubAllGlobals())
it('M4 fails explicitly when persistent video storage is unavailable instead of pretending a memory save succeeded',async()=>{
  vi.stubGlobal('indexedDB',undefined)
  await expect(saveExerciseVideoBlob('session','exercise',new Blob(['clip'],{type:'video/webm'}))).rejects.toThrow('cannot store session videos')
  await expect(loadExerciseVideoBlob('session','exercise')).rejects.toThrow('cannot store session videos')
})

import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const media=vi.hoisted(()=>({save:vi.fn(),load:vi.fn(),remove:vi.fn()}))
vi.mock('./exerciseVideoStore.js',()=>({saveExerciseVideoBlob:media.save,loadExerciseVideoBlob:media.load,removeExerciseVideoBlob:media.remove}))
import { sessionService } from './sessionService.js'
import { mockDb } from './mockDb.js'
const blob=new Blob(['video'],{type:'video/webm'})
const metadata={name:'new.webm',duration:10,audioIncluded:false}
const exercise=()=>mockDb.read().sessions.find(item=>item.id==='s1').exercisePlan[0]
beforeEach(()=>{mockDb.reset();vi.resetAllMocks();media.save.mockResolvedValue('new-id');media.remove.mockResolvedValue();mockDb.mutate(db=>{db.sessions.find(item=>item.id==='s1').exercisePlan=[{id:'video-exercise',name:'Row',videoAttached:true,video:{id:'old-id',name:'old.webm'}}]})})
afterEach(()=>vi.restoreAllMocks())
it('M4 leaves old metadata and media intact when replacement storage fails',async()=>{
  media.save.mockRejectedValue(new Error('Storage unavailable'))
  await expect(sessionService.saveVideo('s1','video-exercise',blob,metadata)).rejects.toThrow('Storage')
  expect(exercise().video.id).toBe('old-id');expect(media.remove).not.toHaveBeenCalled()
})
it('M4 rolls back only the new blob after metadata failure and retries safely',async()=>{
  const storage=vi.spyOn(Storage.prototype,'setItem').mockImplementationOnce(()=>{throw new Error('Quota exceeded')})
  await expect(sessionService.saveVideo('s1','video-exercise',blob,metadata)).rejects.toThrow('Quota')
  expect(exercise().video.id).toBe('old-id');expect(media.remove).toHaveBeenCalledExactlyOnceWith('s1','video-exercise','new-id')
  storage.mockRestore();media.remove.mockClear()
  await sessionService.saveVideo('s1','video-exercise',blob,metadata)
  expect(exercise().video).toMatchObject({id:'new-id',size:blob.size,type:blob.type})
  expect(media.remove).toHaveBeenCalledExactlyOnceWith('s1','video-exercise','old-id')
})
it('M4 rejects stale video writes and completed-session attachment changes',async()=>{
  media.save.mockImplementation(async()=>{mockDb.mutate(db=>{db.sessions.find(item=>item.id==='s1').exercisePlan[0].video.id='winner'});return 'new-id'})
  await expect(sessionService.saveVideo('s1','video-exercise',blob,metadata)).rejects.toThrow('changed')
  expect(exercise().video.id).toBe('winner')
  mockDb.mutate(db=>{db.sessions.find(item=>item.id==='s1').status='completed'})
  await expect(sessionService.removeVideo('s1','video-exercise')).rejects.toThrow('locked')
})

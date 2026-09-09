import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const media=vi.hoisted(()=>({save:vi.fn(),load:vi.fn(),remove:vi.fn(),prune:vi.fn().mockResolvedValue()}))
vi.mock('./exerciseVideoStore.js',()=>({saveExerciseVideoBlob:media.save,loadExerciseVideoBlob:media.load,removeExerciseVideoBlob:media.remove,pruneExerciseVideoBlobs:media.prune}))
import { sessionService } from './sessionService.js'
import { mockDb } from './mockDb.js'
import { pruneExpiredExerciseVideos } from './exerciseVideoRetention.js'
const blob=new Blob(['video'],{type:'video/webm'})
const metadata={name:'new.webm',duration:10,audioIncluded:false}
const exercise=()=>mockDb.read().sessions.find(item=>item.id==='s1').exercisePlan[0]
beforeEach(()=>{mockDb.reset();vi.resetAllMocks();media.save.mockResolvedValue('new-id');media.remove.mockResolvedValue();media.prune.mockResolvedValue();mockDb.mutate(db=>{db.sessions.find(item=>item.id==='s1').exercisePlan=[{id:'video-exercise',name:'Row',videoAttached:true,video:{id:'old-id',name:'old.webm'}}]})})
afterEach(()=>{vi.useRealTimers();vi.restoreAllMocks()})
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

it('retains a recording for seven days from the saved instant and permits completed-session playback only', async () => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-09-09T10:15:00.000Z'))
  media.load.mockResolvedValue(blob)
  await sessionService.saveVideo('s1', 'video-exercise', blob, {
    ...metadata, attachedAt: '2020-01-01T00:00:00.000Z', expiresAt: '2099-01-01T00:00:00.000Z',
  })
  expect(exercise().video).toMatchObject({ attachedAt: '2026-09-09T10:15:00.000Z', expiresAt: '2026-09-16T10:15:00.000Z' })
  expect(media.save).toHaveBeenCalledExactlyOnceWith('s1', 'video-exercise', blob, { expiresAt: '2026-09-16T10:15:00.000Z' })
  mockDb.mutate(db => { db.sessions.find(item => item.id === 's1').status = 'completed' })
  vi.setSystemTime(new Date('2026-09-16T10:14:59.999Z'))
  await expect(sessionService.loadVideo('s1', 'video-exercise')).resolves.toBe(blob)
  expect(media.load).toHaveBeenCalledExactlyOnceWith('s1', 'video-exercise', 'new-id')
  await expect(sessionService.saveVideo('s1', 'video-exercise', blob, metadata)).rejects.toThrow('locked')
  await expect(sessionService.removeVideo('s1', 'video-exercise')).rejects.toThrow('locked')
  media.load.mockClear()
  media.remove.mockClear()
  vi.setSystemTime(new Date('2026-09-16T10:15:00.000Z'))
  await expect(sessionService.loadVideo('s1', 'video-exercise')).rejects.toThrow('expired')
  expect(media.load).not.toHaveBeenCalled()
  expect(exercise()).toMatchObject({ videoAttached: false, video: null })
  expect(media.remove).toHaveBeenCalledExactlyOnceWith('s1', 'video-exercise', 'new-id')
})

it('prunes expired and undated recordings on refresh while retaining failed blob deletions for retry', async () => {
  mockDb.mutate(db => {
    db.sessions.find(item => item.id === 's1').exercisePlan.push(
      { id: 'expired', name: 'Squat', videoAttached: true, video: { id: 'expired-id', attachedAt: '2026-09-01T12:00:00Z' } },
      { id: 'retained', name: 'Press', videoAttached: true, video: { id: 'retained-id', attachedAt: '2026-09-08T12:00:00Z', expiresAt: '2026-09-15T12:00:00Z' } },
    )
  })
  media.remove.mockRejectedValueOnce(new Error('Temporary storage failure'))
  await pruneExpiredExerciseVideos(new Date('2026-09-09T12:00:00Z'))
  const db = mockDb.read()
  expect(db.sessions.find(item => item.id === 's1').exercisePlan).toEqual(expect.arrayContaining([
    expect.objectContaining({ id: 'video-exercise', videoAttached: false, video: null }),
    expect.objectContaining({ id: 'expired', videoAttached: false, video: null }),
    expect.objectContaining({ id: 'retained', videoAttached: true, video: expect.objectContaining({ id: 'retained-id' }) }),
  ]))
  expect(db.pendingVideoDeletions).toEqual([{ sessionId: 's1', exerciseId: 'video-exercise', mediaId: 'old-id' }])
  expect(media.remove).not.toHaveBeenCalledWith('s1', 'retained', 'retained-id')
  media.remove.mockClear()
  await pruneExpiredExerciseVideos(new Date('2026-09-09T12:01:00Z'))
  expect(media.remove).toHaveBeenCalledExactlyOnceWith('s1', 'video-exercise', 'old-id')
  expect(mockDb.read().pendingVideoDeletions).toEqual([])
})

it('does not remove a blob before its expiration metadata and deletion queue can be saved', async () => {
  const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementationOnce(() => { throw new Error('Quota exceeded') })
  await expect(pruneExpiredExerciseVideos(new Date('2026-09-09T12:00:00Z'))).rejects.toThrow('Quota')
  expect(media.remove).not.toHaveBeenCalled()
  expect(exercise().video.id).toBe('old-id')
  storage.mockRestore()
  await pruneExpiredExerciseVideos(new Date('2026-09-09T12:00:00Z'))
  expect(exercise().videoAttached).toBe(false)
  expect(media.remove).toHaveBeenCalledExactlyOnceWith('s1', 'video-exercise', 'old-id')
})

it('keeps a committed replacement usable when the obsolete blob cannot be deleted immediately', async () => {
  media.remove.mockRejectedValueOnce(new Error('Storage temporarily unavailable'))
  await sessionService.saveVideo('s1', 'video-exercise', blob, metadata)
  expect(exercise().video.id).toBe('new-id')
  expect(mockDb.read().pendingVideoDeletions).toEqual([{ sessionId: 's1', exerciseId: 'video-exercise', mediaId: 'old-id' }])
  await pruneExpiredExerciseVideos()
  expect(exercise().video.id).toBe('new-id')
  expect(mockDb.read().pendingVideoDeletions).toEqual([])
})

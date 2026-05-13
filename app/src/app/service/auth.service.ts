import { Injectable } from '@angular/core';
import { BehaviorSubject, from, observable, Observable, of, Subject } from 'rxjs';

@Injectable({
  providedIn: 'root'
})
export class AuthService {

  constructor() { }

  apiKey: BehaviorSubject<string> = new BehaviorSubject('');

  currentApiKey = this.apiKey.asObservable();

  observeApiKey(): Observable<string>{
    return this.currentApiKey;
  }

  getCurrentApiKey(): string {
    return this.apiKey.getValue();
  }

  logUserIn(key: string): void{
    this.apiKey.next(key);
  }
}

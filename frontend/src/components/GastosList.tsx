import { useState, useEffect, useMemo } from 'react'
import Modal from './Modal'
import { apiRequest } from '../api'
import { parseCivilDate } from '../civilDate'

interface Gasto {
  id: number;
  descricao: string;
  valor: number;
  data: string;
  tipo_pagamento: string;
  parcelas: number;
  cartao_id: number;
  pago?: boolean;
  compra_id?: string | null;
  numero_parcela?: number;
  origem?: string;
  external_id?: string | null;
  categoria_id?: number | null;
}

interface Categoria {
  id: number;
  nome: string;
}

interface Cartao {
  id: number;
  nome: string;
  dono: string;
  data_fatura: number;
}

interface GastosListProps {
  apiUrl: string;
  activeProfile: string;
  viewMode: 'diarios' | 'parcelas';
  categorias: Categoria[];
}

interface PaginatedResponse<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

const PAGE_SIZE = 1000;

async function fetchAllGastos(url: string): Promise<Gasto[]> {
  const items: Gasto[] = [];
  let offset = 0;
  let hasMore = true;

  while (hasMore) {
    const separator = url.includes('?') ? '&' : '?';
    const page = await apiRequest<PaginatedResponse<Gasto>>(
      `${url}${separator}limit=${PAGE_SIZE}&offset=${offset}`
    );
    items.push(...page.items);
    offset += page.items.length;
    hasMore = page.items.length > 0 && offset < page.total;
  }

  return items;
}

// Formatter criado uma única vez no nível de módulo (evita recriação a cada render)
const moneyFormatter = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
const formatMoney = (value: number) => moneyFormatter.format(value);

const formatDate = (dateStr: string) => {
  const d = parseCivilDate(dateStr)
  return d.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' }).replace('.', '')
}

const PARCELA_TEST_REGEX = /(?:parcela\s*|\()\d+\/\d+\)?/i;
const PARCELA_EXTRACT_REGEX = /^(.+?)(?:\s*-\s*Parcela\s*|\s*\()(\d+)\/(\d+)\)?\s*$/i;
const PARCELA_NUM_REGEX = /(?:parcela\s*|\()(\d+)\//i;
const isParcela = (gasto: Gasto) =>
  gasto.tipo_pagamento.toLowerCase() === 'credito' &&
  (Boolean(gasto.compra_id) || gasto.parcelas > 1 || PARCELA_TEST_REGEX.test(gasto.descricao));

const referenciaFatura = (data: Date, diaFechamento: number) => {
  const mesesAFrente = data.getDate() >= diaFechamento ? 2 : 1
  const referencia = new Date(data.getFullYear(), data.getMonth() + mesesAFrente, 1)
  return { mes: referencia.getMonth(), ano: referencia.getFullYear() }
}

const pertenceAoMesDaFatura = (gasto: Gasto, cartao: Cartao | undefined, mes: number, ano: number) => {
  const data = parseCivilDate(gasto.data)
  const diaFechamento = cartao?.data_fatura || 15
  const referencia = referenciaFatura(data, diaFechamento)
  return referencia.mes === mes && referencia.ano === ano
}

const getTipoBadge = (tipo: string) => {
  switch (tipo.toLowerCase()) {
    case 'credito': return { label: 'Crédito', color: 'rgba(139, 92, 246, 0.25)', text: '#a78bfa' }
    case 'debito': return { label: 'Débito', color: 'rgba(59, 130, 246, 0.25)', text: '#93c5fd' }
    case 'pix': return { label: 'PIX', color: 'rgba(16, 185, 129, 0.25)', text: '#6ee7b7' }
    default: return { label: tipo, color: 'rgba(255,255,255,0.1)', text: '#fff' }
  }
}

export default function GastosList({ apiUrl, activeProfile, viewMode, categorias }: GastosListProps) {
  const [gastos, setGastos] = useState<Gasto[]>([])
  const [cartoes, setCartoes] = useState<Cartao[]>([])
  const [loading, setLoading] = useState(true)

  // Calendário
  const hojeInicial = new Date()
  const referenciaInicial = referenciaFatura(hojeInicial, 15)
  const [mesAtual, setMesAtual] = useState(viewMode === 'parcelas' ? referenciaInicial.mes : hojeInicial.getMonth())
  const [anoAtual, setAnoAtual] = useState(viewMode === 'parcelas' ? referenciaInicial.ano : hojeInicial.getFullYear())

  // Modal de Parcelas
  const [gastoSelecionado, setGastoSelecionado] = useState<Gasto | null>(null)
  const [parcelasDetalhadas, setParcelasDetalhadas] = useState<Gasto[]>([])
  const [conciliandoId, setConciliandoId] = useState<number | null>(null)

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true)
      try {
        const mesAnt = mesAtual === 0 ? 12 : mesAtual;
        const anoAnt = mesAtual === 0 ? anoAtual - 1 : anoAtual;

        const [gastosAtualData, gastosAntData, cartoesData] = await Promise.all([
          viewMode === 'parcelas'
            ? fetchAllGastos(`${apiUrl}/gastos_diarios/`)
            : fetchAllGastos(`${apiUrl}/gastos_diarios/?mes=${mesAtual + 1}&ano=${anoAtual}`),
          viewMode === 'parcelas'
            ? Promise.resolve([] as Gasto[])
            : fetchAllGastos(`${apiUrl}/gastos_diarios/?mes=${mesAnt}&ano=${anoAnt}`),
          apiRequest<Cartao[]>(`${apiUrl}/cartoes/`)
        ])

        // Remove duplicatas se houver
        const allGastos = [...gastosAtualData, ...gastosAntData];
        const uniqueGastos = Array.from(new Map(allGastos.map(g => [g.id, g])).values());

        setGastos(uniqueGastos)
        setCartoes(cartoesData)
      } catch (err) {
        console.error('Erro ao buscar gastos:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchData()
  }, [apiUrl, mesAtual, anoAtual, viewMode])

  useEffect(() => {
    const hoje = new Date()
    if (viewMode === 'parcelas') {
      const referencia = referenciaFatura(hoje, 15)
      setMesAtual(referencia.mes)
      setAnoAtual(referencia.ano)
    } else {
      setMesAtual(hoje.getMonth())
      setAnoAtual(hoje.getFullYear())
    }
  }, [viewMode])

  // ─── Cálculos memoizados: só recalculados quando as dependências mudarem ───

  const cartoesDoPerfil = useMemo(
    () => cartoes.filter(c => c.dono === activeProfile),
    [cartoes, activeProfile]
  )

  const cartaoIds = useMemo(
    () => new Set(cartoesDoPerfil.map(c => c.id)),
    [cartoesDoPerfil]
  )

  const cartaoNomes = useMemo(
    () => Object.fromEntries(cartoesDoPerfil.map(c => [c.id, c.nome])),
    [cartoesDoPerfil]
  )

  const gastosFiltrados = useMemo(() =>
    gastos
      .filter(g => cartaoIds.has(g.cartao_id))
      .filter(g => {
        const parcela = isParcela(g);
        if (viewMode === 'diarios' && parcela) return false;
        if (viewMode === 'parcelas' && !parcela) return false;
        return true;
      })
      .filter(g => {
        if (viewMode === 'parcelas') {
          const cartao = cartoesDoPerfil.find(c => c.id === g.cartao_id)
          return pertenceAoMesDaFatura(g, cartao, mesAtual, anoAtual)
        }
        const d = parseCivilDate(g.data)
        return d.getMonth() === mesAtual && d.getFullYear() === anoAtual
      })
      .sort((a, b) => {
        const diff = parseCivilDate(b.data).getTime() - parseCivilDate(a.data).getTime();
        return diff !== 0 ? diff : b.id - a.id;
      }),
    [gastos, cartaoIds, cartoesDoPerfil, mesAtual, anoAtual, viewMode]
  )

  const projecaoFatura = useMemo(() =>
    gastos
      .filter(g => cartaoIds.has(g.cartao_id) && g.tipo_pagamento.toLowerCase() === 'credito' && !g.pago)
      .reduce((acc, g) => {
        const d = parseCivilDate(g.data)
        const cartao = cartoesDoPerfil.find(c => c.id === g.cartao_id)
        const diaFechamento = cartao?.data_fatura || 15
        const referencia = referenciaFatura(d, diaFechamento)

        if (referencia.mes === mesAtual && referencia.ano === anoAtual) {
          return acc + g.valor
        }
        return acc
      }, 0),
    [gastos, cartaoIds, cartoesDoPerfil, mesAtual, anoAtual]
  )

  const gastosPorCategoria = useMemo(() => {
    const nomes = new Map(categorias.map(c => [c.id, c.nome]))
    const totais = new Map<string, number>()
    for (const gasto of gastosFiltrados) {
      const nome = gasto.categoria_id ? (nomes.get(gasto.categoria_id) || 'Sem categoria') : 'Sem categoria'
      totais.set(nome, (totais.get(nome) || 0) + gasto.valor)
    }
    return Array.from(totais.entries()).sort((a, b) => b[1] - a[1])
  }, [categorias, gastosFiltrados])

  const gastosPorDia = useMemo(() => {
    const agrupado: Record<string, Gasto[]> = {}
    for (const g of gastosFiltrados) {
      const dia = parseCivilDate(g.data).toLocaleDateString('pt-BR')
      if (!agrupado[dia]) agrupado[dia] = []
      agrupado[dia].push(g)
    }
    return agrupado
  }, [gastosFiltrados])

  const nomeMes = useMemo(
    () => new Date(anoAtual, mesAtual).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' }),
    [anoAtual, mesAtual]
  )

  const { primeiroDia, totalDias } = useMemo(() => ({
    primeiroDia: new Date(anoAtual, mesAtual, 1).getDay(),
    totalDias: new Date(anoAtual, mesAtual + 1, 0).getDate(),
  }), [anoAtual, mesAtual])

  const diasComGasto = useMemo(
    () => new Set(gastosFiltrados.map(g => parseCivilDate(g.data).getDate())),
    [gastosFiltrados]
  )

  // ─── Navegação do calendário ───

  const irMesAnterior = () => {
    if (mesAtual === 0) { setMesAtual(11); setAnoAtual(a => a - 1) }
    else setMesAtual(m => m - 1)
  }
  const irProximoMes = () => {
    if (mesAtual === 11) { setMesAtual(0); setAnoAtual(a => a + 1) }
    else setMesAtual(m => m + 1)
  }
  const irHoje = () => {
    const now = new Date()
    if (viewMode === 'parcelas') {
      const referencia = referenciaFatura(now, 15)
      setMesAtual(referencia.mes)
      setAnoAtual(referencia.ano)
    } else {
      setMesAtual(now.getMonth())
      setAnoAtual(now.getFullYear())
    }
  }

  // ─── Handlers ───

  const handleDelete = async (id: number, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Tem certeza que deseja apagar este gasto? O valor será estornado.')) return
    try {
      await apiRequest(`${apiUrl}/gastos_diarios/${id}`, { method: 'DELETE' })
      setGastos(prev => prev.filter(g => g.id !== id))
    } catch (err) {
      console.error('Erro ao deletar gasto:', err)
      alert(err instanceof Error ? err.message : 'Erro ao deletar gasto')
    }
  }

  const getParcelasInfo = (gasto: Gasto) => {
    const match = gasto.descricao.match(PARCELA_EXTRACT_REGEX)
    if (!match) return null

    const nomeBase = match[1].trim()
    const parcelaAtual = parseInt(match[2])
    const totalParcelas = parseInt(match[3])

    const fonteParcelas = parcelasDetalhadas.length > 0 ? parcelasDetalhadas : gastos
    const parcelasRelacionadas = fonteParcelas
      .filter(g => {
        if (gasto.compra_id) return g.compra_id === gasto.compra_id
        const m = g.descricao.match(PARCELA_EXTRACT_REGEX)
        return m && m[1].trim() === nomeBase && g.cartao_id === gasto.cartao_id
      })
      .sort((a, b) => {
        if (a.numero_parcela && b.numero_parcela) return a.numero_parcela - b.numero_parcela
        const ma = a.descricao.match(PARCELA_NUM_REGEX)
        const mb = b.descricao.match(PARCELA_NUM_REGEX)
        return (ma ? parseInt(ma[1]) : 0) - (mb ? parseInt(mb[1]) : 0)
      })

    const dataInicio = parseCivilDate(parcelasRelacionadas[0]?.data || gasto.data)
    const dataFim = new Date(dataInicio)
    dataFim.setMonth(dataFim.getMonth() + totalParcelas - 1)

    return {
      nomeBase,
      parcelaAtual,
      totalParcelas,
      parcelasRelacionadas,
      valorParcela: gasto.valor,
      valorTotal: parcelasRelacionadas.reduce((total, parcela) => total + parcela.valor, 0),
      dataFim,
      parcelasPagas: parcelasRelacionadas.filter(p => p.pago).length
    }
  }

  const handleClickGasto = async (gasto: Gasto) => {
    if (isParcela(gasto)) {
      setGastoSelecionado(gasto)
      setParcelasDetalhadas([])
      if (gasto.compra_id) {
        try {
          const parcelas = await fetchAllGastos(
            `${apiUrl}/gastos_diarios/?compra_id=${encodeURIComponent(gasto.compra_id)}`
          )
          setParcelasDetalhadas(parcelas)
        } catch (error) {
          console.error('Erro ao buscar parcelas:', error)
        }
      }
    }
  }

  const handleConciliarPagamento = async (parcela: Gasto) => {
    if (parcela.pago) {
      alert('Para reabrir esta parcela, estorne o pagamento nos detalhes da fatura.')
      return
    }
    const novoStatus = !parcela.pago
    if (!confirm('Registrar o pagamento externo? O limite será restaurado sem debitar novamente o saldo.')) return

    setConciliandoId(parcela.id)
    try {
      const resposta = await apiRequest<{ gasto: Gasto }>(
        `${apiUrl}/gastos_diarios/${parcela.id}/conciliar-pagamento`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pago: novoStatus })
        }
      )
      const atualizada = resposta.gasto
      setParcelasDetalhadas(prev => prev.map(p => p.id === atualizada.id ? atualizada : p))
      setGastos(prev => prev.map(p => p.id === atualizada.id ? atualizada : p))
      setGastoSelecionado(prev => prev?.id === atualizada.id ? atualizada : prev)
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao corrigir o pagamento')
    } finally {
      setConciliandoId(null)
    }
  }

  const handleReembolsarCompra = async () => {
    if (!gastoSelecionado?.compra_id) return
    const valor = prompt('Valor do reembolso (deixe vazio para todo o saldo não pago):')
    if (valor === null) return
    const motivo = prompt('Motivo do reembolso:', 'Reembolso solicitado')
    if (!motivo) return
    try {
      await apiRequest(`${apiUrl}/compras/${encodeURIComponent(gastoSelecionado.compra_id)}/reembolsos`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          valor: valor ? Number(valor.replace(',', '.')) : null,
          motivo,
          idempotency_key: crypto.randomUUID(),
        }),
      })
      const atualizadas = await fetchAllGastos(
        `${apiUrl}/gastos_diarios/?compra_id=${encodeURIComponent(gastoSelecionado.compra_id)}`
      )
      setParcelasDetalhadas(atualizadas)
      setGastoSelecionado(atualizadas.find(item => item.id === gastoSelecionado.id) || atualizadas[0] || null)
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Erro ao registrar reembolso')
    }
  }

  const parcelasInfo = gastoSelecionado ? getParcelasInfo(gastoSelecionado) : null

  if (loading) return <p>Carregando gastos...</p>

  return (
    <div>
      {/* Calendário */}
      <div className="glass-panel calendario">
        <div className="calendario-header">
          <button className="cal-nav-btn" onClick={irMesAnterior}>‹</button>
          <div className="cal-titulo" onClick={irHoje}>
            <span className="cal-mes">{nomeMes}</span>
          </div>
          <button className="cal-nav-btn" onClick={irProximoMes}>›</button>
        </div>

        <div className="cal-weekdays">
          {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map(d => (
            <span key={d} className="cal-weekday">{d}</span>
          ))}
        </div>

        <div className="cal-days">
          {Array.from({ length: primeiroDia }).map((_, i) => (
            <span key={`empty-${i}`} className="cal-day empty" />
          ))}
          {Array.from({ length: totalDias }).map((_, i) => {
            const dia = i + 1
            const hoje = new Date()
            const isHoje = dia === hoje.getDate() && mesAtual === hoje.getMonth() && anoAtual === hoje.getFullYear()
            return (
              <span
                key={dia}
                className={`cal-day ${isHoje ? 'hoje' : ''} ${diasComGasto.has(dia) ? 'com-gasto' : ''}`}
              >
                {dia}
                {diasComGasto.has(dia) && <span className="cal-dot" />}
              </span>
            )
          })}
        </div>
      </div>

      {/* Resumo do Mês */}
      <div className="dashboard-grid">
        <div className="glass-panel summary-box hover-lift transition-all" style={{ marginBottom: '1.5rem', borderLeft: '4px solid var(--accent-primary)' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>
            Fatura prevista ({nomeMes})
          </span>
          <span className="summary-value" style={{ color: 'var(--danger)' }}>
            {formatMoney(projecaoFatura)}
          </span>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
            Compras de crédito atribuídas a esta fatura
          </span>
        </div>
        <div className="glass-panel summary-box hover-lift transition-all" style={{ marginBottom: '1.5rem' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', textTransform: 'uppercase', letterSpacing: '1px' }}>Gastos por categoria</span>
          {gastosPorCategoria.length === 0 ? <span style={{ color: 'var(--text-secondary)' }}>Nenhum gasto no mês</span> : gastosPorCategoria.slice(0, 4).map(([nome, total]) => (
            <div key={nome} className="flex-between"><span>{nome}</span><strong>{formatMoney(total)}</strong></div>
          ))}
        </div>
      </div>

      {/* Lista de Gastos */}
      {gastosFiltrados.length === 0 ? (
        <div className="glass-panel" style={{ padding: '2rem', textAlign: 'center' }}>
          <p style={{ color: 'var(--text-secondary)' }}>Nenhum gasto encontrado neste mês.</p>
        </div>
      ) : (
        Object.entries(gastosPorDia).map(([dia, gastosNoDia]) => (
          <div key={dia} style={{ marginBottom: '1.5rem' }}>
            <h3 className="day-header">{dia}</h3>
            <div className="gastos-list">
              {gastosNoDia.map(gasto => {
                const badge = getTipoBadge(gasto.tipo_pagamento)
                const temParcela = isParcela(gasto)
                return (
                  <div
                    key={gasto.id}
                    className={`gasto-item glass-panel transition-all ${temParcela ? 'clickable' : ''}`}
                    onClick={() => handleClickGasto(gasto)}
                  >
                    <div className="gasto-info">
                      <div className="gasto-main">
                        <span className="gasto-descricao">
                          {gasto.descricao}
                          {temParcela && <span className="parcela-icon"> 📊</span>}
                          {(gasto as any).pago && <span className="badge" style={{ background: 'var(--success)', color: 'var(--bg)', marginLeft: '0.5rem', opacity: 0.9, padding: '2px 6px', borderRadius: '4px', fontSize: '0.75rem' }}>Pago</span>}
                          {gasto.origem === 'hermes' && <span className="badge" style={{ marginLeft: '0.5rem' }}>Hermes</span>}
                        </span>
                        <div className="gasto-tags">
                          <span className="gasto-badge" style={{ background: badge.color, color: badge.text }}>
                            {badge.label}
                          </span>
                          <span className="gasto-cartao">{cartaoNomes[gasto.cartao_id] || 'Cartão'}</span>
                          {gasto.categoria_id && <span className="gasto-cartao">{categorias.find(c => c.id === gasto.categoria_id)?.nome || 'Categoria'}</span>}
                        </div>
                      </div>
                      <div className="gasto-right">
                        <span className="gasto-valor">{formatMoney(gasto.valor)}</span>
                        <span className="gasto-data">{formatDate(gasto.data)}</span>
                        <button className="delete-btn" onClick={(e) => handleDelete(gasto.id, e)} title="Apagar gasto">
                          🗑
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        ))
      )}

      {/* Modal de Parcelas */}
      <Modal
        isOpen={!!gastoSelecionado}
        onClose={() => {
          setGastoSelecionado(null)
          setParcelasDetalhadas([])
        }}
        title="Detalhes das Parcelas"
      >
        {parcelasInfo && (
          <div className="parcelas-modal">
            <div className="parcelas-titulo">{parcelasInfo.nomeBase}</div>

            <div className="parcelas-resumo">
              <div className="parcela-stat">
                <span className="stat-label">Valor da Parcela</span>
                <span className="stat-value">{formatMoney(parcelasInfo.valorParcela)}</span>
              </div>
              <div className="parcela-stat">
                <span className="stat-label">Valor Total</span>
                <span className="stat-value">{formatMoney(parcelasInfo.valorTotal)}</span>
              </div>
            </div>

            {gastoSelecionado?.compra_id && (
              <button type="button" className="btn" onClick={handleReembolsarCompra}>
                Registrar reembolso
              </button>
            )}

            {/* Barra de Progresso */}
            <div className="parcela-progresso">
              <div className="progresso-header">
                <span>{parcelasInfo.parcelasPagas} de {parcelasInfo.totalParcelas} parcelas</span>
                <span>{Math.round((parcelasInfo.parcelasPagas / parcelasInfo.totalParcelas) * 100)}%</span>
              </div>
              <div className="progresso-bar">
                <div
                  className="progresso-fill"
                  style={{ width: `${(parcelasInfo.parcelasPagas / parcelasInfo.totalParcelas) * 100}%` }}
                />
              </div>
              <span className="progresso-footer">
                Termina em {parcelasInfo.dataFim.toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })}
              </span>
            </div>

            {/* Timeline de Parcelas */}
            <div className="parcelas-timeline">
              {parcelasInfo.parcelasRelacionadas.map((p, i) => {
                const dataParcela = parseCivilDate(p.data)
                const isPaga = Boolean(p.pago)
                return (
                  <div key={p.id} className={`timeline-item ${isPaga ? 'paga' : 'pendente'}`}>
                    <div className="timeline-dot" />
                    <div className="timeline-info">
                      <span className="timeline-label">
                        Parcela {i + 1}/{parcelasInfo.totalParcelas}
                      </span>
                      <span className="timeline-data">
                        {dataParcela.toLocaleDateString('pt-BR', { month: 'short', year: 'numeric' })}
                      </span>
                    </div>
                    <div className="timeline-valor">
                      <span>{formatMoney(p.valor)}</span>
                      <button
                        type="button"
                        className={`timeline-status timeline-status-btn ${isPaga ? 'paga' : 'pendente'}`}
                        onClick={() => handleConciliarPagamento(p)}
                        disabled={conciliandoId === p.id || isPaga}
                        title={isPaga ? 'Estorne o pagamento pela fatura para reabrir' : 'Registrar pagamento feito fora do sistema'}
                      >
                        {conciliandoId === p.id ? 'Salvando...' : isPaga ? '✓ Paga' : '⏳ Pendente'}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
